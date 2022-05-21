"""
    DLA for ImageNet-1K, implemented in Gluon.
    Original paper: 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.
"""

__all__ = ['DLA', 'dla34', 'dla46c', 'dla46xc', 'dla60', 'dla60x', 'dla60xc', 'dla102', 'dla102x', 'dla102x2', 'dla169']

import os
from mxnet import cpu
from mxnet.gluon import nn, HybridBlock
from .common import conv1x1, conv1x1_block, conv3x3_block, conv7x7_block
from .resnet import ResBlock, ResBottleneck
from .resnext import ResNeXtBottleneck


class DLABottleneck(ResBottleneck):
    """
    DLA bottleneck block for residual path in residual block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    bottleneck_factor : int, default 2
        Bottleneck factor.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 bn_use_global_stats,
                 bottleneck_factor=2,
                 **kwargs):
        super(DLABottleneck, self).__init__(
            in_channels=in_channels,
            out_channels=out_channels,
            strides=strides,
            bn_use_global_stats=bn_use_global_stats,
            bottleneck_factor=bottleneck_factor,
            **kwargs)


class DLABottleneckX(ResNeXtBottleneck):
    """
    DLA ResNeXt-like bottleneck block for residual path in residual block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    cardinality: int, default 32
        Number of groups.
    bottleneck_width: int, default 8
        Width of bottleneck block.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 bn_use_global_stats,
                 cardinality=32,
                 bottleneck_width=8,
                 **kwargs):
        super(DLABottleneckX, self).__init__(
            in_channels=in_channels,
            out_channels=out_channels,
            strides=strides,
            bn_use_global_stats=bn_use_global_stats,
            cardinality=cardinality,
            bottleneck_width=bottleneck_width,
            **kwargs)


class DLAResBlock(HybridBlock):
    """
    DLA residual block with residual connection.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    body_class : nn.Module, default ResBlock
        Residual block body class.
    return_down : bool, default False
        Whether return downsample result.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 bn_use_global_stats,
                 body_class=ResBlock,
                 return_down=False,
                 **kwargs):
        super(DLAResBlock, self).__init__(**kwargs)
        self.return_down = return_down
        self.downsample = (strides > 1)
        self.project = (in_channels != out_channels)

        with self.name_scope():
            self.body = body_class(
                in_channels=in_channels,
                out_channels=out_channels,
                strides=strides,
                bn_use_global_stats=bn_use_global_stats)
            self.activ = nn.Activation("relu")
            if self.downsample:
                self.downsample_pool = nn.MaxPool2D(
                    pool_size=strides,
                    strides=strides)
            if self.project:
                self.project_conv = conv1x1_block(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    bn_use_global_stats=bn_use_global_stats,
                    activation=None)

    def hybrid_forward(self, F, x):
        down = self.downsample_pool(x) if self.downsample else x
        identity = self.project_conv(down) if self.project else down
        if identity is None:
            identity = x
        x = self.body(x)
        x = x + identity
        x = self.activ(x)
        if self.return_down:
            return x, down
        else:
            return x


class DLARoot(HybridBlock):
    """
    DLA root block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    residual : bool
        Whether use residual connection.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 bn_use_global_stats,
                 residual,
                 **kwargs):
        super(DLARoot, self).__init__(**kwargs)
        self.residual = residual

        with self.name_scope():
            self.conv = conv1x1_block(
                in_channels=in_channels,
                out_channels=out_channels,
                bn_use_global_stats=bn_use_global_stats,
                activation=None)
            self.activ = nn.Activation("relu")

    def hybrid_forward(self, F, x2, x1, extra):
        last_branch = x2
        x = F.concat(x2, x1, *extra, dim=1)
        x = self.conv(x)
        if self.residual:
            x = x + last_branch
        x = self.activ(x)
        return x


class DLATree(HybridBlock):
    """
    DLA tree unit. It's like iterative stage.

    Parameters:
    ----------
    levels : int
        Number of levels in the stage.
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    res_body_class : nn.Module
        Residual block body class.
    strides : int or tuple/list of 2 int
        Strides of the convolution in a residual block.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    root_residual : bool
        Whether use residual connection in the root.
    root_dim : int
        Number of input channels in the root block.
    first_tree : bool, default False
        Is this tree stage the first stage in the net.
    input_level : bool, default True
        Is this tree unit the first unit in the stage.
    return_down : bool, default False
        Whether return downsample result.
    """
    def __init__(self,
                 levels,
                 in_channels,
                 out_channels,
                 res_body_class,
                 strides,
                 bn_use_global_stats,
                 root_residual,
                 root_dim=0,
                 first_tree=False,
                 input_level=True,
                 return_down=False,
                 **kwargs):
        super(DLATree, self).__init__(**kwargs)
        self.return_down = return_down
        self.add_down = (input_level and not first_tree)
        self.root_level = (levels == 1)

        if root_dim == 0:
            root_dim = 2 * out_channels
        if self.add_down:
            root_dim += in_channels

        with self.name_scope():
            if self.root_level:
                self.tree1 = DLAResBlock(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    strides=strides,
                    bn_use_global_stats=bn_use_global_stats,
                    body_class=res_body_class,
                    return_down=True)
                self.tree2 = DLAResBlock(
                    in_channels=out_channels,
                    out_channels=out_channels,
                    strides=1,
                    bn_use_global_stats=bn_use_global_stats,
                    body_class=res_body_class,
                    return_down=False)
            else:
                self.tree1 = DLATree(
                    levels=levels - 1,
                    in_channels=in_channels,
                    out_channels=out_channels,
                    res_body_class=res_body_class,
                    strides=strides,
                    bn_use_global_stats=bn_use_global_stats,
                    root_residual=root_residual,
                    root_dim=0,
                    input_level=False,
                    return_down=True)
                self.tree2 = DLATree(
                    levels=levels - 1,
                    in_channels=out_channels,
                    out_channels=out_channels,
                    res_body_class=res_body_class,
                    strides=1,
                    bn_use_global_stats=bn_use_global_stats,
                    root_residual=root_residual,
                    root_dim=root_dim + out_channels,
                    input_level=False,
                    return_down=False)
            if self.root_level:
                self.root = DLARoot(
                    in_channels=root_dim,
                    out_channels=out_channels,
                    bn_use_global_stats=bn_use_global_stats,
                    residual=root_residual)

    def hybrid_forward(self, F, x, extra=None):
        extra = [] if extra is None else extra
        x1, down = self.tree1(x)
        if self.add_down:
            extra.append(down)
        if self.root_level:
            x2 = self.tree2(x1)
            x = self.root(x2, x1, extra)
        else:
            extra.append(x1)
            x = self.tree2(x1, extra)
        if self.return_down:
            return x, down
        else:
            return x


class DLAInitBlock(HybridBlock):
    """
    DLA specific initial block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool, default False
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 bn_use_global_stats=False,
                 **kwargs):
        super(DLAInitBlock, self).__init__(**kwargs)
        mid_channels = out_channels // 2

        with self.name_scope():
            self.conv1 = conv7x7_block(
                in_channels=in_channels,
                out_channels=mid_channels,
                bn_use_global_stats=bn_use_global_stats)
            self.conv2 = conv3x3_block(
                in_channels=mid_channels,
                out_channels=mid_channels,
                bn_use_global_stats=bn_use_global_stats)
            self.conv3 = conv3x3_block(
                in_channels=mid_channels,
                out_channels=out_channels,
                strides=2,
                bn_use_global_stats=bn_use_global_stats)

    def hybrid_forward(self, F, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        return x


class DLA(HybridBlock):
    """
    DLA model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    levels : int
        Number of levels in each stage.
    channels : list of int
        Number of output channels for each stage.
    init_block_channels : int
        Number of output channels for the initial unit.
    res_body_class : nn.Module
        Residual block body class.
    residual_root : bool
        Whether use residual connection in the root blocks.
    bn_use_global_stats : bool, default False
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
        Useful for fine-tuning.
    in_channels : int, default 3
        Number of input channels.
    in_size : tuple of two ints, default (224, 224)
        Spatial size of the expected input image.
    classes : int, default 1000
        Number of classification classes.
    """
    def __init__(self,
                 levels,
                 channels,
                 init_block_channels,
                 res_body_class,
                 residual_root,
                 bn_use_global_stats=False,
                 in_channels=3,
                 in_size=(224, 224),
                 classes=1000,
                 **kwargs):
        super(DLA, self).__init__(**kwargs)
        self.in_size = in_size
        self.classes = classes

        with self.name_scope():
            self.features = nn.HybridSequential(prefix="")
            self.features.add(DLAInitBlock(
                in_channels=in_channels,
                out_channels=init_block_channels,
                bn_use_global_stats=bn_use_global_stats))
            in_channels = init_block_channels

            for i in range(len(levels)):
                levels_i = levels[i]
                out_channels = channels[i]
                first_tree = (i == 0)
                self.features.add(DLATree(
                    levels=levels_i,
                    in_channels=in_channels,
                    out_channels=out_channels,
                    res_body_class=res_body_class,
                    strides=2,
                    bn_use_global_stats=bn_use_global_stats,
                    root_residual=residual_root,
                    first_tree=first_tree))
                in_channels = out_channels

            self.features.add(nn.AvgPool2D(
                pool_size=7,
                strides=1))

            self.output = nn.HybridSequential(prefix="")
            self.output.add(conv1x1(
                in_channels=in_channels,
                out_channels=classes,
                use_bias=True))
            self.output.add(nn.Flatten())

    def hybrid_forward(self, F, x):
        x = self.features(x)
        x = self.output(x)
        return x


def get_dla(levels,
            channels,
            res_body_class,
            residual_root=False,
            model_name=None,
            pretrained=False,
            ctx=cpu(),
            root=os.path.join("~", ".mxnet", "models"),
            **kwargs):
    """
    Create DLA model with specific parameters.

    Parameters:
    ----------
    levels : int
        Number of levels in each stage.
    channels : list of int
        Number of output channels for each stage.
    res_body_class : nn.Module
        Residual block body class.
    residual_root : bool, default False
        Whether use residual connection in the root blocks.
    model_name : str or None, default None
        Model name for loading pretrained model.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    init_block_channels = 32

    net = DLA(
        levels=levels,
        channels=channels,
        init_block_channels=init_block_channels,
        res_body_class=res_body_class,
        residual_root=residual_root,
        **kwargs)

    if pretrained:
        if (model_name is None) or (not model_name):
            raise ValueError("Parameter `model_name` should be properly initialized for loading pretrained model.")
        from .model_store import get_model_file
        net.load_parameters(
            filename=get_model_file(
                model_name=model_name,
                local_model_store_dir_path=root),
            ctx=ctx)

    return net


def dla34(**kwargs):
    """
    DLA-34 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 2, 2, 1], channels=[64, 128, 256, 512], res_body_class=ResBlock, model_name="dla34",
                   **kwargs)


def dla46c(**kwargs):
    """
    DLA-46-C model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 2, 2, 1], channels=[64, 64, 128, 256], res_body_class=DLABottleneck, model_name="dla46c",
                   **kwargs)


def dla46xc(**kwargs):
    """
    DLA-X-46-C model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 2, 2, 1], channels=[64, 64, 128, 256], res_body_class=DLABottleneckX,
                   model_name="dla46xc", **kwargs)


def dla60(**kwargs):
    """
    DLA-60 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 2, 3, 1], channels=[128, 256, 512, 1024], res_body_class=DLABottleneck,
                   model_name="dla60", **kwargs)


def dla60x(**kwargs):
    """
    DLA-X-60 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 2, 3, 1], channels=[128, 256, 512, 1024], res_body_class=DLABottleneckX,
                   model_name="dla60x", **kwargs)


def dla60xc(**kwargs):
    """
    DLA-X-60-C model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 2, 3, 1], channels=[64, 64, 128, 256], res_body_class=DLABottleneckX,
                   model_name="dla60xc", **kwargs)


def dla102(**kwargs):
    """
    DLA-102 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 3, 4, 1], channels=[128, 256, 512, 1024], res_body_class=DLABottleneck,
                   residual_root=True, model_name="dla102", **kwargs)


def dla102x(**kwargs):
    """
    DLA-X-102 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[1, 3, 4, 1], channels=[128, 256, 512, 1024], res_body_class=DLABottleneckX,
                   residual_root=True, model_name="dla102x", **kwargs)


def dla102x2(**kwargs):
    """
    DLA-X2-102 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    class DLABottleneckX64(DLABottleneckX):
        def __init__(self, in_channels, out_channels, strides, bn_use_global_stats):
            super(DLABottleneckX64, self).__init__(in_channels, out_channels, strides, bn_use_global_stats,
                                                   cardinality=64)

    return get_dla(levels=[1, 3, 4, 1], channels=[128, 256, 512, 1024], res_body_class=DLABottleneckX64,
                   residual_root=True, model_name="dla102x2", **kwargs)


def dla169(**kwargs):
    """
    DLA-169 model from 'Deep Layer Aggregation,' https://arxiv.org/abs/1707.06484.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_dla(levels=[2, 3, 5, 1], channels=[128, 256, 512, 1024], res_body_class=DLABottleneck,
                   residual_root=True, model_name="dla169", **kwargs)


def _test():
    import numpy as np
    import mxnet as mx

    pretrained = False

    models = [
        dla34,
        dla46c,
        dla46xc,
        dla60,
        dla60x,
        dla60xc,
        dla102,
        dla102x,
        dla102x2,
        dla169,
    ]

    for model in models:

        net = model(pretrained=pretrained)

        ctx = mx.cpu()
        if not pretrained:
            net.initialize(ctx=ctx)

        # net.hybridize()
        net_params = net.collect_params()
        weight_count = 0
        for param in net_params.values():
            if (param.shape is None) or (not param._differentiable):
                continue
            weight_count += np.prod(param.shape)
        print("m={}, {}".format(model.__name__, weight_count))
        assert (model != dla34 or weight_count == 15742104)
        assert (model != dla46c or weight_count == 1301400)
        assert (model != dla46xc or weight_count == 1068440)
        assert (model != dla60 or weight_count == 22036632)
        assert (model != dla60x or weight_count == 17352344)
        assert (model != dla60xc or weight_count == 1319832)
        assert (model != dla102 or weight_count == 33268888)
        assert (model != dla102x or weight_count == 26309272)
        assert (model != dla102x2 or weight_count == 41282200)
        assert (model != dla169 or weight_count == 53389720)

        x = mx.nd.zeros((1, 3, 224, 224), ctx=ctx)
        y = net(x)
        assert (y.shape == (1, 1000))


if __name__ == "__main__":
    _test()
