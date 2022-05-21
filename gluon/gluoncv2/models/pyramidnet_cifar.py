"""
    PyramidNet for CIFAR/SVHN, implemented in Gluon.
    Original paper: 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.
"""

__all__ = ['CIFARPyramidNet', 'pyramidnet110_a48_cifar10', 'pyramidnet110_a48_cifar100', 'pyramidnet110_a48_svhn',
           'pyramidnet110_a84_cifar10', 'pyramidnet110_a84_cifar100', 'pyramidnet110_a84_svhn',
           'pyramidnet110_a270_cifar10', 'pyramidnet110_a270_cifar100', 'pyramidnet110_a270_svhn',
           'pyramidnet164_a270_bn_cifar10', 'pyramidnet164_a270_bn_cifar100', 'pyramidnet164_a270_bn_svhn',
           'pyramidnet200_a240_bn_cifar10', 'pyramidnet200_a240_bn_cifar100', 'pyramidnet200_a240_bn_svhn',
           'pyramidnet236_a220_bn_cifar10', 'pyramidnet236_a220_bn_cifar100', 'pyramidnet236_a220_bn_svhn',
           'pyramidnet272_a200_bn_cifar10', 'pyramidnet272_a200_bn_cifar100', 'pyramidnet272_a200_bn_svhn']

import os
from mxnet import cpu
from mxnet.gluon import nn, HybridBlock
from .common import conv3x3_block
from .preresnet import PreResActivation
from .pyramidnet import PyrUnit


class CIFARPyramidNet(HybridBlock):
    """
    PyramidNet model for CIFAR from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    channels : list of list of int
        Number of output channels for each unit.
    init_block_channels : int
        Number of output channels for the initial unit.
    bottleneck : bool
        Whether to use a bottleneck or simple block in units.
    bn_use_global_stats : bool, default False
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
        Useful for fine-tuning.
    in_channels : int, default 3
        Number of input channels.
    in_size : tuple of two ints, default (32, 32)
        Spatial size of the expected input image.
    classes : int, default 10
        Number of classification classes.
    """
    def __init__(self,
                 channels,
                 init_block_channels,
                 bottleneck,
                 bn_use_global_stats=False,
                 in_channels=3,
                 in_size=(32, 32),
                 classes=10,
                 **kwargs):
        super(CIFARPyramidNet, self).__init__(**kwargs)
        self.in_size = in_size
        self.classes = classes

        with self.name_scope():
            self.features = nn.HybridSequential(prefix="")
            self.features.add(conv3x3_block(
                in_channels=in_channels,
                out_channels=init_block_channels,
                bn_use_global_stats=bn_use_global_stats,
                activation=None))
            in_channels = init_block_channels
            for i, channels_per_stage in enumerate(channels):
                stage = nn.HybridSequential(prefix="stage{}_".format(i + 1))
                with stage.name_scope():
                    for j, out_channels in enumerate(channels_per_stage):
                        strides = 2 if (j == 0) and (i != 0) else 1
                        stage.add(PyrUnit(
                            in_channels=in_channels,
                            out_channels=out_channels,
                            strides=strides,
                            bn_use_global_stats=bn_use_global_stats,
                            bottleneck=bottleneck))
                        in_channels = out_channels
                self.features.add(stage)
            self.features.add(PreResActivation(
                in_channels=in_channels,
                bn_use_global_stats=bn_use_global_stats))
            self.features.add(nn.AvgPool2D(
                pool_size=8,
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


def get_pyramidnet_cifar(classes,
                         blocks,
                         alpha,
                         bottleneck,
                         model_name=None,
                         pretrained=False,
                         ctx=cpu(),
                         root=os.path.join("~", ".mxnet", "models"),
                         **kwargs):
    """
    Create PyramidNet for CIFAR model with specific parameters.

    Parameters:
    ----------
    classes : int
        Number of classification classes.
    blocks : int
        Number of blocks.
    alpha : int
        PyramidNet's alpha value.
    bottleneck : bool
        Whether to use a bottleneck or simple block in units.
    model_name : str or None, default None
        Model name for loading pretrained model.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    assert (classes in [10, 100])

    if bottleneck:
        assert ((blocks - 2) % 9 == 0)
        layers = [(blocks - 2) // 9] * 3
    else:
        assert ((blocks - 2) % 6 == 0)
        layers = [(blocks - 2) // 6] * 3
    init_block_channels = 16

    growth_add = float(alpha) / float(sum(layers))
    from functools import reduce
    channels = reduce(
        lambda xi, yi: xi + [[(i + 1) * growth_add + xi[-1][-1] for i in list(range(yi))]],
        layers,
        [[init_block_channels]])[1:]
    channels = [[int(round(cij)) for cij in ci] for ci in channels]

    if bottleneck:
        channels = [[cij * 4 for cij in ci] for ci in channels]

    net = CIFARPyramidNet(
        channels=channels,
        init_block_channels=init_block_channels,
        bottleneck=bottleneck,
        classes=classes,
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


def pyramidnet110_a48_cifar10(classes=10, **kwargs):
    """
    PyramidNet-110 (a=48) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=48,
        bottleneck=False,
        model_name="pyramidnet110_a48_cifar10",
        **kwargs)


def pyramidnet110_a48_cifar100(classes=100, **kwargs):
    """
    PyramidNet-110 (a=48) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=48,
        bottleneck=False,
        model_name="pyramidnet110_a48_cifar100",
        **kwargs)


def pyramidnet110_a48_svhn(classes=10, **kwargs):
    """
    PyramidNet-110 (a=48) model for SVHN from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=48,
        bottleneck=False,
        model_name="pyramidnet110_a48_svhn",
        **kwargs)


def pyramidnet110_a84_cifar10(classes=10, **kwargs):
    """
    PyramidNet-110 (a=84) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=84,
        bottleneck=False,
        model_name="pyramidnet110_a84_cifar10",
        **kwargs)


def pyramidnet110_a84_cifar100(classes=100, **kwargs):
    """
    PyramidNet-110 (a=84) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=84,
        bottleneck=False,
        model_name="pyramidnet110_a84_cifar100",
        **kwargs)


def pyramidnet110_a84_svhn(classes=10, **kwargs):
    """
    PyramidNet-110 (a=84) model for SVHN from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=84,
        bottleneck=False,
        model_name="pyramidnet110_a84_svhn",
        **kwargs)


def pyramidnet110_a270_cifar10(classes=10, **kwargs):
    """
    PyramidNet-110 (a=270) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=270,
        bottleneck=False,
        model_name="pyramidnet110_a270_cifar10",
        **kwargs)


def pyramidnet110_a270_cifar100(classes=100, **kwargs):
    """
    PyramidNet-110 (a=270) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=270,
        bottleneck=False,
        model_name="pyramidnet110_a270_cifar100",
        **kwargs)


def pyramidnet110_a270_svhn(classes=10, **kwargs):
    """
    PyramidNet-110 (a=270) model for SVHN from 'Deep Pyramidal Residual Networks,' https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=110,
        alpha=270,
        bottleneck=False,
        model_name="pyramidnet110_a270_svhn",
        **kwargs)


def pyramidnet164_a270_bn_cifar10(classes=10, **kwargs):
    """
    PyramidNet-164 (a=270, bn) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=164,
        alpha=270,
        bottleneck=True,
        model_name="pyramidnet164_a270_bn_cifar10",
        **kwargs)


def pyramidnet164_a270_bn_cifar100(classes=100, **kwargs):
    """
    PyramidNet-164 (a=270, bn) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=164,
        alpha=270,
        bottleneck=True,
        model_name="pyramidnet164_a270_bn_cifar100",
        **kwargs)


def pyramidnet164_a270_bn_svhn(classes=10, **kwargs):
    """
    PyramidNet-164 (a=270, bn) model for SVHN from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=164,
        alpha=270,
        bottleneck=True,
        model_name="pyramidnet164_a270_bn_svhn",
        **kwargs)


def pyramidnet200_a240_bn_cifar10(classes=10, **kwargs):
    """
    PyramidNet-200 (a=240, bn) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=200,
        alpha=240,
        bottleneck=True,
        model_name="pyramidnet200_a240_bn_cifar10",
        **kwargs)


def pyramidnet200_a240_bn_cifar100(classes=100, **kwargs):
    """
    PyramidNet-200 (a=240, bn) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=200,
        alpha=240,
        bottleneck=True,
        model_name="pyramidnet200_a240_bn_cifar100",
        **kwargs)


def pyramidnet200_a240_bn_svhn(classes=10, **kwargs):
    """
    PyramidNet-200 (a=240, bn) model for SVHN from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=200,
        alpha=240,
        bottleneck=True,
        model_name="pyramidnet200_a240_bn_svhn",
        **kwargs)


def pyramidnet236_a220_bn_cifar10(classes=10, **kwargs):
    """
    PyramidNet-236 (a=220, bn) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=236,
        alpha=220,
        bottleneck=True,
        model_name="pyramidnet236_a220_bn_cifar10",
        **kwargs)


def pyramidnet236_a220_bn_cifar100(classes=100, **kwargs):
    """
    PyramidNet-236 (a=220, bn) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=236,
        alpha=220,
        bottleneck=True,
        model_name="pyramidnet236_a220_bn_cifar100",
        **kwargs)


def pyramidnet236_a220_bn_svhn(classes=10, **kwargs):
    """
    PyramidNet-236 (a=220, bn) model for SVHN from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=236,
        alpha=220,
        bottleneck=True,
        model_name="pyramidnet236_a220_bn_svhn",
        **kwargs)


def pyramidnet272_a200_bn_cifar10(classes=10, **kwargs):
    """
    PyramidNet-272 (a=200, bn) model for CIFAR-10 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=272,
        alpha=200,
        bottleneck=True,
        model_name="pyramidnet272_a200_bn_cifar10",
        **kwargs)


def pyramidnet272_a200_bn_cifar100(classes=100, **kwargs):
    """
    PyramidNet-272 (a=200, bn) model for CIFAR-100 from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 100
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=272,
        alpha=200,
        bottleneck=True,
        model_name="pyramidnet272_a200_bn_cifar100",
        **kwargs)


def pyramidnet272_a200_bn_svhn(classes=10, **kwargs):
    """
    PyramidNet-272 (a=200, bn) model for SVHN from 'Deep Pyramidal Residual Networks,'
    https://arxiv.org/abs/1610.02915.

    Parameters:
    ----------
    classes : int, default 10
        Number of classification classes.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_pyramidnet_cifar(
        classes=classes,
        blocks=272,
        alpha=200,
        bottleneck=True,
        model_name="pyramidnet272_a200_bn_svhn",
        **kwargs)


def _test():
    import numpy as np
    import mxnet as mx

    pretrained = False

    models = [
        (pyramidnet110_a48_cifar10, 10),
        (pyramidnet110_a48_cifar100, 100),
        (pyramidnet110_a48_svhn, 10),
        (pyramidnet110_a84_cifar10, 10),
        (pyramidnet110_a84_cifar100, 100),
        (pyramidnet110_a84_svhn, 10),
        (pyramidnet110_a270_cifar10, 10),
        (pyramidnet110_a270_cifar100, 100),
        (pyramidnet110_a270_svhn, 10),
        (pyramidnet164_a270_bn_cifar10, 10),
        (pyramidnet164_a270_bn_cifar100, 100),
        (pyramidnet164_a270_bn_svhn, 10),
        (pyramidnet200_a240_bn_cifar10, 10),
        (pyramidnet200_a240_bn_cifar100, 100),
        (pyramidnet200_a240_bn_svhn, 10),
        (pyramidnet236_a220_bn_cifar10, 10),
        (pyramidnet236_a220_bn_cifar100, 100),
        (pyramidnet236_a220_bn_svhn, 10),
        (pyramidnet272_a200_bn_cifar10, 10),
        (pyramidnet272_a200_bn_cifar100, 100),
        (pyramidnet272_a200_bn_svhn, 10),
    ]

    for model, classes in models:

        net = model(pretrained=pretrained, classes=classes)

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
        assert (model != pyramidnet110_a48_cifar10 or weight_count == 1772706)
        assert (model != pyramidnet110_a48_cifar100 or weight_count == 1778556)
        assert (model != pyramidnet110_a48_svhn or weight_count == 1772706)
        assert (model != pyramidnet110_a84_cifar10 or weight_count == 3904446)
        assert (model != pyramidnet110_a84_cifar100 or weight_count == 3913536)
        assert (model != pyramidnet110_a84_svhn or weight_count == 3904446)
        assert (model != pyramidnet110_a270_cifar10 or weight_count == 28485477)
        assert (model != pyramidnet110_a270_cifar100 or weight_count == 28511307)
        assert (model != pyramidnet110_a270_svhn or weight_count == 28485477)
        assert (model != pyramidnet164_a270_bn_cifar10 or weight_count == 27216021)
        assert (model != pyramidnet164_a270_bn_cifar100 or weight_count == 27319071)
        assert (model != pyramidnet164_a270_bn_svhn or weight_count == 27216021)
        assert (model != pyramidnet200_a240_bn_cifar10 or weight_count == 26752702)
        assert (model != pyramidnet200_a240_bn_cifar100 or weight_count == 26844952)
        assert (model != pyramidnet200_a240_bn_svhn or weight_count == 26752702)
        assert (model != pyramidnet236_a220_bn_cifar10 or weight_count == 26969046)
        assert (model != pyramidnet236_a220_bn_cifar100 or weight_count == 27054096)
        assert (model != pyramidnet236_a220_bn_svhn or weight_count == 26969046)
        assert (model != pyramidnet272_a200_bn_cifar10 or weight_count == 26210842)
        assert (model != pyramidnet272_a200_bn_cifar100 or weight_count == 26288692)
        assert (model != pyramidnet272_a200_bn_svhn or weight_count == 26210842)

        x = mx.nd.zeros((1, 3, 32, 32), ctx=ctx)
        y = net(x)
        assert (y.shape == (1, classes))


if __name__ == "__main__":
    _test()
