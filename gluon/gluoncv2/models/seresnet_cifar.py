"""
    SE-ResNet for CIFAR/SVHN, implemented in Gluon.
    Original paper: 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.
"""

__all__ = ['CIFARSEResNet', 'seresnet20_cifar10', 'seresnet20_cifar100', 'seresnet20_svhn',
           'seresnet56_cifar10', 'seresnet56_cifar100', 'seresnet56_svhn',
           'seresnet110_cifar10', 'seresnet110_cifar100', 'seresnet110_svhn',
           'seresnet164bn_cifar10', 'seresnet164bn_cifar100', 'seresnet164bn_svhn',
           'seresnet272bn_cifar10', 'seresnet272bn_cifar100', 'seresnet272bn_svhn',
           'seresnet542bn_cifar10', 'seresnet542bn_cifar100', 'seresnet542bn_svhn',
           'seresnet1001_cifar10', 'seresnet1001_cifar100', 'seresnet1001_svhn',
           'seresnet1202_cifar10', 'seresnet1202_cifar100', 'seresnet1202_svhn']

import os
from mxnet import cpu
from mxnet.gluon import nn, HybridBlock
from .common import conv3x3_block
from .seresnet import SEResUnit


class CIFARSEResNet(HybridBlock):
    """
    SE-ResNet model for CIFAR from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
        super(CIFARSEResNet, self).__init__(**kwargs)
        self.in_size = in_size
        self.classes = classes

        with self.name_scope():
            self.features = nn.HybridSequential(prefix="")
            self.features.add(conv3x3_block(
                in_channels=in_channels,
                out_channels=init_block_channels,
                bn_use_global_stats=bn_use_global_stats))
            in_channels = init_block_channels
            for i, channels_per_stage in enumerate(channels):
                stage = nn.HybridSequential(prefix="stage{}_".format(i + 1))
                with stage.name_scope():
                    for j, out_channels in enumerate(channels_per_stage):
                        strides = 2 if (j == 0) and (i != 0) else 1
                        stage.add(SEResUnit(
                            in_channels=in_channels,
                            out_channels=out_channels,
                            strides=strides,
                            bn_use_global_stats=bn_use_global_stats,
                            bottleneck=bottleneck,
                            conv1_stride=False))
                        in_channels = out_channels
                self.features.add(stage)
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


def get_seresnet_cifar(classes,
                       blocks,
                       bottleneck,
                       model_name=None,
                       pretrained=False,
                       ctx=cpu(),
                       root=os.path.join("~", ".mxnet", "models"),
                       **kwargs):
    """
    Create SE-ResNet model for CIFAR with specific parameters.

    Parameters:
    ----------
    classes : int
        Number of classification classes.
    blocks : int
        Number of blocks.
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

    channels_per_layers = [16, 32, 64]
    init_block_channels = 16

    channels = [[ci] * li for (ci, li) in zip(channels_per_layers, layers)]

    if bottleneck:
        channels = [[cij * 4 for cij in ci] for ci in channels]

    net = CIFARSEResNet(
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


def seresnet20_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-20 model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=20, bottleneck=False, model_name="seresnet20_cifar10", **kwargs)


def seresnet20_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-20 model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=20, bottleneck=False, model_name="seresnet20_cifar100", **kwargs)


def seresnet20_svhn(classes=10, **kwargs):
    """
    SE-ResNet-20 model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=20, bottleneck=False, model_name="seresnet20_svhn", **kwargs)


def seresnet56_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-56 model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=56, bottleneck=False, model_name="seresnet56_cifar10", **kwargs)


def seresnet56_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-56 model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=56, bottleneck=False, model_name="seresnet56_cifar100", **kwargs)


def seresnet56_svhn(classes=10, **kwargs):
    """
    SE-ResNet-56 model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=56, bottleneck=False, model_name="seresnet56_svhn", **kwargs)


def seresnet110_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-110 model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=110, bottleneck=False, model_name="seresnet110_cifar10", **kwargs)


def seresnet110_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-110 model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=110, bottleneck=False, model_name="seresnet110_cifar100",
                              **kwargs)


def seresnet110_svhn(classes=10, **kwargs):
    """
    SE-ResNet-110 model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=110, bottleneck=False, model_name="seresnet110_svhn", **kwargs)


def seresnet164bn_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-164(BN) model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=164, bottleneck=True, model_name="seresnet164bn_cifar10",
                              **kwargs)


def seresnet164bn_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-164(BN) model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=164, bottleneck=True, model_name="seresnet164bn_cifar100",
                              **kwargs)


def seresnet164bn_svhn(classes=10, **kwargs):
    """
    SE-ResNet-164(BN) model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=164, bottleneck=True, model_name="seresnet164bn_svhn", **kwargs)


def seresnet272bn_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-272(BN) model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=272, bottleneck=True, model_name="seresnet272bn_cifar10",
                              **kwargs)


def seresnet272bn_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-272(BN) model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=272, bottleneck=True, model_name="seresnet272bn_cifar100",
                              **kwargs)


def seresnet272bn_svhn(classes=10, **kwargs):
    """
    SE-ResNet-272(BN) model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=272, bottleneck=True, model_name="seresnet272bn_svhn", **kwargs)


def seresnet542bn_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-542(BN) model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=542, bottleneck=True, model_name="seresnet542bn_cifar10",
                              **kwargs)


def seresnet542bn_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-542(BN) model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=542, bottleneck=True, model_name="seresnet542bn_cifar100",
                              **kwargs)


def seresnet542bn_svhn(classes=10, **kwargs):
    """
    SE-ResNet-542(BN) model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=542, bottleneck=True, model_name="seresnet542bn_svhn", **kwargs)


def seresnet1001_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-1001 model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=1001, bottleneck=True, model_name="seresnet1001_cifar10",
                              **kwargs)


def seresnet1001_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-1001 model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=1001, bottleneck=True, model_name="seresnet1001_cifar100",
                              **kwargs)


def seresnet1001_svhn(classes=10, **kwargs):
    """
    SE-ResNet-1001 model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=1001, bottleneck=True, model_name="seresnet1001_svhn", **kwargs)


def seresnet1202_cifar10(classes=10, **kwargs):
    """
    SE-ResNet-1202 model for CIFAR-10 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=1202, bottleneck=False, model_name="seresnet1202_cifar10",
                              **kwargs)


def seresnet1202_cifar100(classes=100, **kwargs):
    """
    SE-ResNet-1202 model for CIFAR-100 from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=1202, bottleneck=False, model_name="seresnet1202_cifar100",
                              **kwargs)


def seresnet1202_svhn(classes=10, **kwargs):
    """
    SE-ResNet-1202 model for SVHN from 'Squeeze-and-Excitation Networks,' https://arxiv.org/abs/1709.01507.

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
    return get_seresnet_cifar(classes=classes, blocks=1202, bottleneck=False, model_name="seresnet1202_svhn", **kwargs)


def _test():
    import numpy as np
    import mxnet as mx

    pretrained = False

    models = [
        (seresnet20_cifar10, 10),
        (seresnet20_cifar100, 100),
        (seresnet20_svhn, 10),
        (seresnet56_cifar10, 10),
        (seresnet56_cifar100, 100),
        (seresnet56_svhn, 10),
        (seresnet110_cifar10, 10),
        (seresnet110_cifar100, 100),
        (seresnet110_svhn, 10),
        (seresnet164bn_cifar10, 10),
        (seresnet164bn_cifar100, 100),
        (seresnet164bn_svhn, 10),
        (seresnet272bn_cifar10, 10),
        (seresnet272bn_cifar100, 100),
        (seresnet272bn_svhn, 10),
        (seresnet542bn_cifar10, 10),
        (seresnet542bn_cifar100, 100),
        (seresnet542bn_svhn, 10),
        (seresnet1001_cifar10, 10),
        (seresnet1001_cifar100, 100),
        (seresnet1001_svhn, 10),
        (seresnet1202_cifar10, 10),
        (seresnet1202_cifar100, 100),
        (seresnet1202_svhn, 10),
    ]

    for model, classes in models:

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
        assert (model != seresnet20_cifar10 or weight_count == 274847)
        assert (model != seresnet20_cifar100 or weight_count == 280697)
        assert (model != seresnet20_svhn or weight_count == 274847)
        assert (model != seresnet56_cifar10 or weight_count == 862889)
        assert (model != seresnet56_cifar100 or weight_count == 868739)
        assert (model != seresnet56_svhn or weight_count == 862889)
        assert (model != seresnet110_cifar10 or weight_count == 1744952)
        assert (model != seresnet110_cifar100 or weight_count == 1750802)
        assert (model != seresnet110_svhn or weight_count == 1744952)
        assert (model != seresnet164bn_cifar10 or weight_count == 1906258)
        assert (model != seresnet164bn_cifar100 or weight_count == 1929388)
        assert (model != seresnet164bn_svhn or weight_count == 1906258)
        assert (model != seresnet272bn_cifar10 or weight_count == 3153826)
        assert (model != seresnet272bn_cifar100 or weight_count == 3176956)
        assert (model != seresnet272bn_svhn or weight_count == 3153826)
        assert (model != seresnet542bn_cifar10 or weight_count == 6272746)
        assert (model != seresnet542bn_cifar100 or weight_count == 6295876)
        assert (model != seresnet542bn_svhn or weight_count == 6272746)
        assert (model != seresnet1001_cifar10 or weight_count == 11574910)
        assert (model != seresnet1001_cifar100 or weight_count == 11598040)
        assert (model != seresnet1001_svhn or weight_count == 11574910)
        assert (model != seresnet1202_cifar10 or weight_count == 19582226)
        assert (model != seresnet1202_cifar100 or weight_count == 19588076)
        assert (model != seresnet1202_svhn or weight_count == 19582226)

        x = mx.nd.zeros((1, 3, 32, 32), ctx=ctx)
        y = net(x)
        assert (y.shape == (1, classes))


if __name__ == "__main__":
    _test()
