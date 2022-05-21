"""
    AirNeXt for ImageNet-1K, implemented in Gluon.
    Original paper: 'Attention Inspiring Receptive-Fields Network for Learning Invariant Representations,'
    https://ieeexplore.ieee.org/document/8510896.
"""

__all__ = ['AirNeXt', 'airnext50_32x4d_r2', 'airnext101_32x4d_r2', 'airnext101_32x4d_r16']

import os
import math
from mxnet import cpu
from mxnet.gluon import nn, HybridBlock
from .common import conv1x1_block, conv3x3_block
from .airnet import AirBlock, AirInitBlock


class AirNeXtBottleneck(HybridBlock):
    """
    AirNet bottleneck block for residual path in ResNet unit.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    cardinality: int
        Number of groups.
    bottleneck_width: int
        Width of bottleneck block.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    ratio: int
        Air compression ratio.
    in_size : tuple of 2 int
        Spatial size of the input tensor for the bilinear upsampling operation.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 cardinality,
                 bottleneck_width,
                 bn_use_global_stats,
                 ratio,
                 in_size,
                 **kwargs):
        super(AirNeXtBottleneck, self).__init__(**kwargs)
        mid_channels = out_channels // 4
        D = int(math.floor(mid_channels * (bottleneck_width / 64.0)))
        group_width = cardinality * D
        self.use_air_block = (strides == 1 and mid_channels < 512)

        with self.name_scope():
            self.conv1 = conv1x1_block(
                in_channels=in_channels,
                out_channels=group_width,
                bn_use_global_stats=bn_use_global_stats)
            self.conv2 = conv3x3_block(
                in_channels=group_width,
                out_channels=group_width,
                strides=strides,
                groups=cardinality,
                bn_use_global_stats=bn_use_global_stats)
            self.conv3 = conv1x1_block(
                in_channels=group_width,
                out_channels=out_channels,
                bn_use_global_stats=bn_use_global_stats,
                activation=None)
            if self.use_air_block:
                self.air = AirBlock(
                    in_channels=in_channels,
                    out_channels=group_width,
                    groups=(cardinality // ratio),
                    bn_use_global_stats=bn_use_global_stats,
                    ratio=ratio,
                    in_size=in_size)

    def hybrid_forward(self, F, x):
        if self.use_air_block:
            att = self.air(x)
        x = self.conv1(x)
        x = self.conv2(x)
        if self.use_air_block:
            x = x * att
        x = self.conv3(x)
        return x


class AirNeXtUnit(HybridBlock):
    """
    AirNet unit with residual connection.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    cardinality: int
        Number of groups.
    bottleneck_width: int
        Width of bottleneck block.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    ratio: int
        Air compression ratio.
    in_size : tuple of 2 int
        Spatial size of the input tensor for the bilinear upsampling operation.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 cardinality,
                 bottleneck_width,
                 bn_use_global_stats,
                 ratio,
                 in_size,
                 **kwargs):
        super(AirNeXtUnit, self).__init__(**kwargs)
        self.resize_identity = (in_channels != out_channels) or (strides != 1)

        with self.name_scope():
            self.body = AirNeXtBottleneck(
                in_channels=in_channels,
                out_channels=out_channels,
                strides=strides,
                cardinality=cardinality,
                bottleneck_width=bottleneck_width,
                bn_use_global_stats=bn_use_global_stats,
                ratio=ratio,
                in_size=in_size)
            if self.resize_identity:
                self.identity_conv = conv1x1_block(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    strides=strides,
                    bn_use_global_stats=bn_use_global_stats,
                    activation=None)
            self.activ = nn.Activation("relu")

    def hybrid_forward(self, F, x):
        if self.resize_identity:
            identity = self.identity_conv(x)
        else:
            identity = x
        x = self.body(x)
        x = x + identity
        x = self.activ(x)
        return x


class AirNeXt(HybridBlock):
    """
    AirNet model from 'Attention Inspiring Receptive-Fields Network for Learning Invariant Representations,'
    https://ieeexplore.ieee.org/document/8510896.

    Parameters:
    ----------
    channels : list of list of int
        Number of output channels for each unit.
    init_block_channels : int
        Number of output channels for the initial unit.
    cardinality: int
        Number of groups.
    bottleneck_width: int
        Width of bottleneck block.
    ratio: int
        Air compression ratio.
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
                 channels,
                 init_block_channels,
                 cardinality,
                 bottleneck_width,
                 ratio,
                 bn_use_global_stats=False,
                 in_channels=3,
                 in_size=(224, 224),
                 classes=1000,
                 **kwargs):
        super(AirNeXt, self).__init__(**kwargs)
        self.in_size = in_size
        self.classes = classes

        with self.name_scope():
            self.features = nn.HybridSequential(prefix="")
            self.features.add(AirInitBlock(
                in_channels=in_channels,
                out_channels=init_block_channels,
                bn_use_global_stats=bn_use_global_stats))
            in_channels = init_block_channels
            in_size = tuple([x // 4 for x in in_size])
            for i, channels_per_stage in enumerate(channels):
                stage = nn.HybridSequential(prefix="stage{}_".format(i + 1))
                with stage.name_scope():
                    for j, out_channels in enumerate(channels_per_stage):
                        strides = 2 if (j == 0) and (i != 0) else 1
                        stage.add(AirNeXtUnit(
                            in_channels=in_channels,
                            out_channels=out_channels,
                            strides=strides,
                            cardinality=cardinality,
                            bottleneck_width=bottleneck_width,
                            bn_use_global_stats=bn_use_global_stats,
                            ratio=ratio,
                            in_size=in_size))
                        in_channels = out_channels
                        in_size = tuple([x // strides for x in in_size])
                self.features.add(stage)
            self.features.add(nn.AvgPool2D(
                pool_size=7,
                strides=1))

            self.output = nn.HybridSequential(prefix="")
            self.output.add(nn.Flatten())
            self.output.add(nn.Dense(
                units=classes,
                in_units=in_channels))

    def hybrid_forward(self, F, x):
        x = self.features(x)
        x = self.output(x)
        return x


def get_airnext(blocks,
                cardinality,
                bottleneck_width,
                base_channels,
                ratio,
                model_name=None,
                pretrained=False,
                ctx=cpu(),
                root=os.path.join("~", ".mxnet", "models"),
                **kwargs):
    """
    Create AirNet model with specific parameters.

    Parameters:
    ----------
    blocks : int
        Number of blocks.
    cardinality: int
        Number of groups.
    bottleneck_width: int
        Width of bottleneck block.
    base_channels: int
        Base number of channels.
    ratio: int
        Air compression ratio.
    model_name : str or None, default None
        Model name for loading pretrained model.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """

    if blocks == 50:
        layers = [3, 4, 6, 3]
    elif blocks == 101:
        layers = [3, 4, 23, 3]
    else:
        raise ValueError("Unsupported AirNeXt with number of blocks: {}".format(blocks))

    bottleneck_expansion = 4
    init_block_channels = base_channels
    channels_per_layers = [base_channels * (2 ** i) * bottleneck_expansion for i in range(len(layers))]

    channels = [[ci] * li for (ci, li) in zip(channels_per_layers, layers)]

    net = AirNeXt(
        channels=channels,
        init_block_channels=init_block_channels,
        cardinality=cardinality,
        bottleneck_width=bottleneck_width,
        ratio=ratio,
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


def airnext50_32x4d_r2(**kwargs):
    """
    AirNeXt50-32x4d (r=2) model from 'Attention Inspiring Receptive-Fields Network for Learning Invariant
    Representations,' https://ieeexplore.ieee.org/document/8510896.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_airnext(
        blocks=50,
        cardinality=32,
        bottleneck_width=4,
        base_channels=64,
        ratio=2,
        model_name="airnext50_32x4d_r2",
        **kwargs)


def airnext101_32x4d_r2(**kwargs):
    """
    AirNeXt101-32x4d (r=2) model from 'Attention Inspiring Receptive-Fields Network for Learning Invariant
    Representations,' https://ieeexplore.ieee.org/document/8510896.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_airnext(
        blocks=101,
        cardinality=32,
        bottleneck_width=4,
        base_channels=64,
        ratio=2,
        model_name="airnext101_32x4d_r2",
        **kwargs)


def airnext101_32x4d_r16(**kwargs):
    """
    AirNeXt101-32x4d (r=16) model from 'Attention Inspiring Receptive-Fields Network for Learning Invariant
    Representations,' https://ieeexplore.ieee.org/document/8510896.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_airnext(
        blocks=101,
        cardinality=32,
        bottleneck_width=4,
        base_channels=64,
        ratio=16,
        model_name="airnext101_32x4d_r16",
        **kwargs)


def _test():
    import numpy as np
    import mxnet as mx

    pretrained = False

    models = [
        airnext50_32x4d_r2,
        airnext101_32x4d_r2,
        airnext101_32x4d_r16,
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
        assert (model != airnext50_32x4d_r2 or weight_count == 27604296)
        assert (model != airnext101_32x4d_r2 or weight_count == 54099272)
        assert (model != airnext101_32x4d_r16 or weight_count == 45456456)

        x = mx.nd.zeros((1, 3, 224, 224), ctx=ctx)
        y = net(x)
        assert (y.shape == (1, 1000))


if __name__ == "__main__":
    _test()
