"""
    PolyNet for ImageNet-1K, implemented in Gluon.
    Original paper: 'PolyNet: A Pursuit of Structural Diversity in Very Deep Networks,'
    https://arxiv.org/abs/1611.05725.
"""

__all__ = ['PolyNet', 'polynet']

import os
from mxnet import cpu
from mxnet.gluon import nn, HybridBlock
from mxnet.gluon.contrib.nn import HybridConcurrent
from .common import ConvBlock, conv1x1_block, conv3x3_block, ParametricSequential, ParametricConcurrent


class PolyConv(HybridBlock):
    """
    PolyNet specific convolution block. A block that is used inside poly-N (poly-2, poly-3, and so on) modules.
    The Convolution layer is shared between all Inception blocks inside a poly-N module. BatchNorm layers are not
    shared between Inception blocks and therefore the number of BatchNorm layers is equal to the number of Inception
    blocks inside a poly-N module.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    kernel_size : int or tuple/list of 2 int
        Convolution window size.
    strides : int or tuple/list of 2 int
        Strides of the convolution.
    padding : int or tuple/list of 2 int
        Padding value for convolution layer.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    num_blocks : int
        Number of blocks (BatchNorm layers).
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 strides,
                 padding,
                 bn_use_global_stats,
                 num_blocks,
                 **kwargs):
        super(PolyConv, self).__init__(**kwargs)
        with self.name_scope():
            self.conv = nn.Conv2D(
                channels=out_channels,
                kernel_size=kernel_size,
                strides=strides,
                padding=padding,
                use_bias=False,
                in_channels=in_channels)
            for i in range(num_blocks):
                setattr(self, "bn{}".format(i + 1), nn.BatchNorm(
                    in_channels=out_channels,
                    use_global_stats=bn_use_global_stats))
            self.activ = nn.Activation("relu")

    def hybrid_forward(self, F, x, index):
        x = self.conv(x)
        bn = getattr(self, "bn{}".format(index + 1))
        x = bn(x)
        x = self.activ(x)
        return x


def poly_conv1x1(in_channels,
                 out_channels,
                 bn_use_global_stats,
                 num_blocks):
    """
    1x1 version of the PolyNet specific convolution block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    num_blocks : int
        Number of blocks (BatchNorm layers).
    """
    return PolyConv(
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=1,
        strides=1,
        padding=0,
        bn_use_global_stats=bn_use_global_stats,
        num_blocks=num_blocks)


class MaxPoolBranch(HybridBlock):
    """
    PolyNet specific max pooling branch block.
    """
    def __init__(self,
                 **kwargs):
        super(MaxPoolBranch, self).__init__(**kwargs)
        with self.name_scope():
            self.pool = nn.MaxPool2D(
                pool_size=3,
                strides=2,
                padding=0)

    def hybrid_forward(self, F, x):
        x = self.pool(x)
        return x


class Conv1x1Branch(HybridBlock):
    """
    PolyNet specific convolutional 1x1 branch block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 bn_use_global_stats,
                 **kwargs):
        super(Conv1x1Branch, self).__init__(**kwargs)
        with self.name_scope():
            self.conv = conv1x1_block(
                in_channels=in_channels,
                out_channels=out_channels,
                bn_use_global_stats=bn_use_global_stats)

    def hybrid_forward(self, F, x):
        x = self.conv(x)
        return x


class Conv3x3Branch(HybridBlock):
    """
    PolyNet specific convolutional 3x3 branch block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 in_channels,
                 out_channels,
                 bn_use_global_stats,
                 **kwargs):
        super(Conv3x3Branch, self).__init__(**kwargs)
        with self.name_scope():
            self.conv = conv3x3_block(
                in_channels=in_channels,
                out_channels=out_channels,
                strides=2,
                padding=0,
                bn_use_global_stats=bn_use_global_stats)

    def hybrid_forward(self, F, x):
        x = self.conv(x)
        return x


class ConvSeqBranch(HybridBlock):
    """
    PolyNet specific convolutional sequence branch block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels_list : list of tuple of int
        List of numbers of output channels.
    kernel_size_list : list of tuple of int or tuple of tuple/list of 2 int
        List of convolution window sizes.
    strides_list : list of tuple of int or tuple of tuple/list of 2 int
        List of strides of the convolution.
    padding_list : list of tuple of int or tuple of tuple/list of 2 int
        List of padding values for convolution layers.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 in_channels,
                 out_channels_list,
                 kernel_size_list,
                 strides_list,
                 padding_list,
                 bn_use_global_stats,
                 **kwargs):
        super(ConvSeqBranch, self).__init__(**kwargs)
        assert (len(out_channels_list) == len(kernel_size_list))
        assert (len(out_channels_list) == len(strides_list))
        assert (len(out_channels_list) == len(padding_list))

        with self.name_scope():
            self.conv_list = nn.HybridSequential(prefix="")
            for i, (out_channels, kernel_size, strides, padding) in enumerate(zip(
                    out_channels_list, kernel_size_list, strides_list, padding_list)):
                self.conv_list.add(ConvBlock(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    kernel_size=kernel_size,
                    strides=strides,
                    padding=padding,
                    bn_use_global_stats=bn_use_global_stats))
                in_channels = out_channels

    def hybrid_forward(self, F, x):
        x = self.conv_list(x)
        return x


class PolyConvSeqBranch(HybridBlock):
    """
    PolyNet specific convolutional sequence branch block with internal PolyNet specific convolution blocks.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels_list : list of tuple of int
        List of numbers of output channels.
    kernel_size_list : list of tuple of int or tuple of tuple/list of 2 int
        List of convolution window sizes.
    strides_list : list of tuple of int or tuple of tuple/list of 2 int
        List of strides of the convolution.
    padding_list : list of tuple of int or tuple of tuple/list of 2 int
        List of padding values for convolution layers.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    num_blocks : int
        Number of blocks for PolyConv.
    """
    def __init__(self,
                 in_channels,
                 out_channels_list,
                 kernel_size_list,
                 strides_list,
                 padding_list,
                 bn_use_global_stats,
                 num_blocks,
                 **kwargs):
        super(PolyConvSeqBranch, self).__init__(**kwargs)
        assert (len(out_channels_list) == len(kernel_size_list))
        assert (len(out_channels_list) == len(strides_list))
        assert (len(out_channels_list) == len(padding_list))

        with self.name_scope():
            self.conv_list = ParametricSequential(prefix="")
            for i, (out_channels, kernel_size, strides, padding) in enumerate(zip(
                    out_channels_list, kernel_size_list, strides_list, padding_list)):
                self.conv_list.add(PolyConv(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    kernel_size=kernel_size,
                    strides=strides,
                    padding=padding,
                    bn_use_global_stats=bn_use_global_stats,
                    num_blocks=num_blocks))
                in_channels = out_channels

    def hybrid_forward(self, F, x, index):
        x = self.conv_list(x, index)
        return x


class TwoWayABlock(HybridBlock):
    """
    PolyNet type Inception-A block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(TwoWayABlock, self).__init__(**kwargs)
        in_channels = 384

        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(32, 48, 64),
                kernel_size_list=(1, 3, 3),
                strides_list=(1, 1, 1),
                padding_list=(0, 1, 1),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(32, 32),
                kernel_size_list=(1, 3),
                strides_list=(1, 1),
                padding_list=(0, 1),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(Conv1x1Branch(
                in_channels=in_channels,
                out_channels=32,
                bn_use_global_stats=bn_use_global_stats))
            self.conv = conv1x1_block(
                in_channels=128,
                out_channels=in_channels,
                bn_use_global_stats=bn_use_global_stats,
                activation=None)

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        x = self.conv(x)
        return x


class TwoWayBBlock(HybridBlock):
    """
    PolyNet type Inception-B block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(TwoWayBBlock, self).__init__(**kwargs)
        in_channels = 1152

        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(128, 160, 192),
                kernel_size_list=(1, (1, 7), (7, 1)),
                strides_list=(1, 1, 1),
                padding_list=(0, (0, 3), (3, 0)),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(Conv1x1Branch(
                in_channels=in_channels,
                out_channels=192,
                bn_use_global_stats=bn_use_global_stats))
            self.conv = conv1x1_block(
                in_channels=384,
                out_channels=in_channels,
                bn_use_global_stats=bn_use_global_stats,
                activation=None)

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        x = self.conv(x)
        return x


class TwoWayCBlock(HybridBlock):
    """
    PolyNet type Inception-C block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(TwoWayCBlock, self).__init__(**kwargs)
        in_channels = 2048

        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(192, 224, 256),
                kernel_size_list=(1, (1, 3), (3, 1)),
                strides_list=(1, 1, 1),
                padding_list=(0, (0, 1), (1, 0)),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(Conv1x1Branch(
                in_channels=in_channels,
                out_channels=192,
                bn_use_global_stats=bn_use_global_stats))
            self.conv = conv1x1_block(
                in_channels=448,
                out_channels=in_channels,
                bn_use_global_stats=bn_use_global_stats,
                activation=None)

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        x = self.conv(x)
        return x


class PolyPreBBlock(HybridBlock):
    """
    PolyNet type PolyResidual-Pre-B block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    num_blocks : int
        Number of blocks (BatchNorm layers).
    """
    def __init__(self,
                 bn_use_global_stats,
                 num_blocks,
                 **kwargs):
        super(PolyPreBBlock, self).__init__(**kwargs)
        in_channels = 1152

        with self.name_scope():
            self.branches = ParametricConcurrent(axis=1, prefix="")
            self.branches.add(PolyConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(128, 160, 192),
                kernel_size_list=(1, (1, 7), (7, 1)),
                strides_list=(1, 1, 1),
                padding_list=(0, (0, 3), (3, 0)),
                bn_use_global_stats=bn_use_global_stats,
                num_blocks=num_blocks))
            self.branches.add(poly_conv1x1(
                in_channels=in_channels,
                out_channels=192,
                bn_use_global_stats=bn_use_global_stats,
                num_blocks=num_blocks))

    def hybrid_forward(self, F, x, index):
        x = self.branches(x, index)
        return x


class PolyPreCBlock(HybridBlock):
    """
    PolyNet type PolyResidual-Pre-C block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    out_channels : int
        Number of output channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    num_blocks : int
        Number of blocks (BatchNorm layers).
    """
    def __init__(self,
                 bn_use_global_stats,
                 num_blocks,
                 **kwargs):
        super(PolyPreCBlock, self).__init__(**kwargs)
        in_channels = 2048

        with self.name_scope():
            self.branches = ParametricConcurrent(axis=1, prefix="")
            self.branches.add(PolyConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(192, 224, 256),
                kernel_size_list=(1, (1, 3), (3, 1)),
                strides_list=(1, 1, 1),
                padding_list=(0, (0, 1), (1, 0)),
                bn_use_global_stats=bn_use_global_stats,
                num_blocks=num_blocks))
            self.branches.add(poly_conv1x1(
                in_channels=in_channels,
                out_channels=192,
                bn_use_global_stats=bn_use_global_stats,
                num_blocks=num_blocks))

    def hybrid_forward(self, F, x, index):
        x = self.branches(x, index)
        return x


def poly_res_b_block(bn_use_global_stats):
    """
    PolyNet type PolyResidual-Res-B block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    return conv1x1_block(
        in_channels=384,
        out_channels=1152,
        strides=1,
        bn_use_global_stats=bn_use_global_stats,
        activation=None)


def poly_res_c_block(bn_use_global_stats):
    """
    PolyNet type PolyResidual-Res-C block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    return conv1x1_block(
        in_channels=448,
        out_channels=2048,
        strides=1,
        bn_use_global_stats=bn_use_global_stats,
        activation=None)


class MultiResidual(HybridBlock):
    """
    Base class for constructing N-way modules (2-way, 3-way, and so on). Actually it is for 2-way modules.

    Parameters:
    ----------
    scale : float, default 1.0
        Scale value for each residual branch.
    res_block : HybridBlock class
        Residual branch block.
    num_blocks : int
        Number of residual branches.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 scale,
                 res_block,
                 num_blocks,
                 bn_use_global_stats,
                 **kwargs):
        super(MultiResidual, self).__init__(**kwargs)
        assert (num_blocks >= 1)
        self.scale = scale
        self.num_blocks = num_blocks

        with self.name_scope():
            for i in range(num_blocks):
                setattr(self, "res_block{}".format(i + 1), res_block(bn_use_global_stats=bn_use_global_stats))
            self.activ = nn.Activation("relu")

    def hybrid_forward(self, F, x):
        out = x
        for i in range(self.num_blocks):
            res_block = getattr(self, "res_block{}".format(i + 1))
            out = out + self.scale * res_block(x)
        out = self.activ(out)
        return out


class PolyResidual(HybridBlock):
    """
    The other base class for constructing N-way poly-modules. Actually it is for 3-way poly-modules.

    Parameters:
    ----------
    scale : float, default 1.0
        Scale value for each residual branch.
    res_block : HybridBlock class
        Residual branch block.
    num_blocks : int
        Number of residual branches.
    pre_block : HybridBlock class
        Preliminary block.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 scale,
                 res_block,
                 num_blocks,
                 pre_block,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyResidual, self).__init__(**kwargs)
        assert (num_blocks >= 1)
        self.scale = scale
        self.num_blocks = num_blocks

        with self.name_scope():
            self.pre_block = pre_block(
                bn_use_global_stats=bn_use_global_stats,
                num_blocks=num_blocks)
            for i in range(num_blocks):
                setattr(self, "res_block{}".format(i + 1), res_block(bn_use_global_stats=bn_use_global_stats))
            self.activ = nn.Activation("relu")

    def hybrid_forward(self, F, x):
        out = x
        for index in range(self.num_blocks):
            x = self.pre_block(x, index)
            res_block = getattr(self, "res_block{}".format(index + 1))
            x = res_block(x)
            out = out + self.scale * x
            x = self.activ(x)
        out = self.activ(out)
        return out


class PolyBaseUnit(HybridBlock):
    """
    PolyNet unit base class.

    Parameters:
    ----------
    two_way_scale : float
        Scale value for 2-way stage.
    two_way_block : HybridBlock class
        Residual branch block for 2-way-stage.
    poly_scale : float, default 0.0
        Scale value for 2-way stage.
    poly_res_block : HybridBlock class, default None
        Residual branch block for poly-stage.
    poly_pre_block : HybridBlock class, default None
        Preliminary branch block for poly-stage.
    bn_use_global_stats : bool, default False
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 two_way_scale,
                 two_way_block,
                 poly_scale=0.0,
                 poly_res_block=None,
                 poly_pre_block=None,
                 bn_use_global_stats=False,
                 **kwargs):
        super(PolyBaseUnit, self).__init__(**kwargs)

        with self.name_scope():
            if poly_res_block is not None:
                assert (poly_scale != 0.0)
                assert (poly_pre_block is not None)
                self.poly = PolyResidual(
                    scale=poly_scale,
                    res_block=poly_res_block,
                    num_blocks=3,
                    pre_block=poly_pre_block,
                    bn_use_global_stats=bn_use_global_stats)
            else:
                assert (poly_scale == 0.0)
                assert (poly_pre_block is None)
                self.poly = None
            self.twoway = MultiResidual(
                scale=two_way_scale,
                res_block=two_way_block,
                num_blocks=2,
                bn_use_global_stats=bn_use_global_stats)

    def hybrid_forward(self, F, x):
        if self.poly is not None:
            x = self.poly(x)
        x = self.twoway(x)
        return x


class PolyAUnit(PolyBaseUnit):
    """
    PolyNet type A unit.

    Parameters:
    ----------
    two_way_scale : float
        Scale value for 2-way stage.
    poly_scale : float
        Scale value for 2-way stage.
    bn_use_global_stats : bool, default False
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 two_way_scale,
                 poly_scale=0.0,
                 bn_use_global_stats=False,
                 **kwargs):
        super(PolyAUnit, self).__init__(
            two_way_scale=two_way_scale,
            two_way_block=TwoWayABlock,
            bn_use_global_stats=bn_use_global_stats,
            **kwargs)
        assert (poly_scale == 0.0)


class PolyBUnit(PolyBaseUnit):
    """
    PolyNet type B unit.

    Parameters:
    ----------
    two_way_scale : float
        Scale value for 2-way stage.
    poly_scale : float
        Scale value for 2-way stage.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 two_way_scale,
                 poly_scale,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyBUnit, self).__init__(
            two_way_scale=two_way_scale,
            two_way_block=TwoWayBBlock,
            poly_scale=poly_scale,
            poly_res_block=poly_res_b_block,
            poly_pre_block=PolyPreBBlock,
            bn_use_global_stats=bn_use_global_stats,
            **kwargs)


class PolyCUnit(PolyBaseUnit):
    """
    PolyNet type C unit.

    Parameters:
    ----------
    two_way_scale : float
        Scale value for 2-way stage.
    poly_scale : float
        Scale value for 2-way stage.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 two_way_scale,
                 poly_scale,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyCUnit, self).__init__(
            two_way_scale=two_way_scale,
            two_way_block=TwoWayCBlock,
            poly_scale=poly_scale,
            poly_res_block=poly_res_c_block,
            poly_pre_block=PolyPreCBlock,
            bn_use_global_stats=bn_use_global_stats,
            **kwargs)


class ReductionAUnit(HybridBlock):
    """
    PolyNet type Reduction-A unit.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(ReductionAUnit, self).__init__(**kwargs)
        in_channels = 384

        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(256, 256, 384),
                kernel_size_list=(1, 3, 3),
                strides_list=(1, 1, 2),
                padding_list=(0, 1, 0),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(384,),
                kernel_size_list=(3,),
                strides_list=(2,),
                padding_list=(0,),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(MaxPoolBranch())

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        return x


class ReductionBUnit(HybridBlock):
    """
    PolyNet type Reduction-B unit.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(ReductionBUnit, self).__init__(**kwargs)
        in_channels = 1152

        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(256, 256, 256),
                kernel_size_list=(1, 3, 3),
                strides_list=(1, 1, 2),
                padding_list=(0, 1, 0),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(256, 256),
                kernel_size_list=(1, 3),
                strides_list=(1, 2),
                padding_list=(0, 0),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(ConvSeqBranch(
                in_channels=in_channels,
                out_channels_list=(256, 384),
                kernel_size_list=(1, 3),
                strides_list=(1, 2),
                padding_list=(0, 0),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(MaxPoolBranch())

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        return x


class PolyBlock3a(HybridBlock):
    """
    PolyNet type Mixed-3a block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyBlock3a, self).__init__(**kwargs)
        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(MaxPoolBranch())
            self.branches.add(Conv3x3Branch(
                in_channels=64,
                out_channels=96,
                bn_use_global_stats=bn_use_global_stats))

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        return x


class PolyBlock4a(HybridBlock):
    """
    PolyNet type Mixed-4a block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyBlock4a, self).__init__(**kwargs)
        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(ConvSeqBranch(
                in_channels=160,
                out_channels_list=(64, 96),
                kernel_size_list=(1, 3),
                strides_list=(1, 1),
                padding_list=(0, 0),
                bn_use_global_stats=bn_use_global_stats))
            self.branches.add(ConvSeqBranch(
                in_channels=160,
                out_channels_list=(64, 64, 64, 96),
                kernel_size_list=(1, (7, 1), (1, 7), 3),
                strides_list=(1, 1, 1, 1),
                padding_list=(0, (3, 0), (0, 3), 0),
                bn_use_global_stats=bn_use_global_stats))

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        return x


class PolyBlock5a(HybridBlock):
    """
    PolyNet type Mixed-5a block.

    Parameters:
    ----------
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyBlock5a, self).__init__(**kwargs)
        with self.name_scope():
            self.branches = HybridConcurrent(axis=1, prefix="")
            self.branches.add(MaxPoolBranch())
            self.branches.add(Conv3x3Branch(
                in_channels=192,
                out_channels=192,
                bn_use_global_stats=bn_use_global_stats))

    def hybrid_forward(self, F, x):
        x = self.branches(x)
        return x


class PolyInitBlock(HybridBlock):
    """
    PolyNet specific initial block.

    Parameters:
    ----------
    in_channels : int
        Number of input channels.
    bn_use_global_stats : bool
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    """
    def __init__(self,
                 in_channels,
                 bn_use_global_stats,
                 **kwargs):
        super(PolyInitBlock, self).__init__(**kwargs)
        with self.name_scope():
            self.conv1 = conv3x3_block(
                in_channels=in_channels,
                out_channels=32,
                strides=2,
                padding=0,
                bn_use_global_stats=bn_use_global_stats)
            self.conv2 = conv3x3_block(
                in_channels=32,
                out_channels=32,
                padding=0,
                bn_use_global_stats=bn_use_global_stats)
            self.conv3 = conv3x3_block(
                in_channels=32,
                out_channels=64,
                bn_use_global_stats=bn_use_global_stats)
            self.block1 = PolyBlock3a(bn_use_global_stats=bn_use_global_stats)
            self.block2 = PolyBlock4a(bn_use_global_stats=bn_use_global_stats)
            self.block3 = PolyBlock5a(bn_use_global_stats=bn_use_global_stats)

    def hybrid_forward(self, F, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        return x


class PolyNet(HybridBlock):
    """
    PolyNet model from 'PolyNet: A Pursuit of Structural Diversity in Very Deep Networks,'
    https://arxiv.org/abs/1611.05725.

    Parameters:
    ----------
    two_way_scales : list of list of floats
        Two way scale values for each normal unit.
    poly_scales : list of list of floats
        Three way scale values for each normal unit.
    dropout_rate : float, default 0.2
        Fraction of the input units to drop. Must be a number between 0 and 1.
    bn_use_global_stats : bool, default False
        Whether global moving statistics is used instead of local batch-norm for BatchNorm layers.
    in_channels : int, default 3
        Number of input channels.
    in_size : tuple of two ints, default (331, 331)
        Spatial size of the expected input image.
    classes : int, default 1000
        Number of classification classes.
    """
    def __init__(self,
                 two_way_scales,
                 poly_scales,
                 dropout_rate=0.2,
                 bn_use_global_stats=False,
                 in_channels=3,
                 in_size=(331, 331),
                 classes=1000,
                 **kwargs):
        super(PolyNet, self).__init__(**kwargs)
        self.in_size = in_size
        self.classes = classes
        normal_units = [PolyAUnit, PolyBUnit, PolyCUnit]
        reduction_units = [ReductionAUnit, ReductionBUnit]

        with self.name_scope():
            self.features = nn.HybridSequential(prefix="")
            self.features.add(PolyInitBlock(
                in_channels=in_channels,
                bn_use_global_stats=bn_use_global_stats))

            for i, (two_way_scales_per_stage, poly_scales_per_stage) in enumerate(zip(two_way_scales, poly_scales)):
                stage = nn.HybridSequential(prefix="stage{}_".format(i + 1))
                with stage.name_scope():
                    for j, (two_way_scale, poly_scale) in enumerate(zip(two_way_scales_per_stage, poly_scales_per_stage)):
                        if (j == 0) and (i != 0):
                            unit = reduction_units[i - 1]
                            stage.add(unit(bn_use_global_stats=bn_use_global_stats))
                        else:
                            unit = normal_units[i]
                            stage.add(unit(
                                two_way_scale=two_way_scale,
                                poly_scale=poly_scale,
                                bn_use_global_stats=bn_use_global_stats))
                self.features.add(stage)

            self.features.add(nn.AvgPool2D(
                pool_size=9,
                strides=1))

            self.output = nn.HybridSequential(prefix="")
            self.output.add(nn.Flatten())
            self.output.add(nn.Dropout(rate=dropout_rate))
            self.output.add(nn.Dense(
                units=classes,
                in_units=2048))

    def hybrid_forward(self, F, x):
        x = self.features(x)
        x = self.output(x)
        return x


def get_polynet(model_name=None,
                pretrained=False,
                ctx=cpu(),
                root=os.path.join("~", ".mxnet", "models"),
                **kwargs):
    """
    Create PolyNet model with specific parameters.

    Parameters:
    ----------
    model_name : str or None, default None
        Model name for loading pretrained model.
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    two_way_scales = [
        [1.000000, 0.992308, 0.984615, 0.976923, 0.969231, 0.961538, 0.953846, 0.946154, 0.938462, 0.930769],
        [0.000000, 0.915385, 0.900000, 0.884615, 0.869231, 0.853846, 0.838462, 0.823077, 0.807692, 0.792308, 0.776923],
        [0.000000, 0.761538, 0.746154, 0.730769, 0.715385, 0.700000]]
    poly_scales = [
        [0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000],
        [0.000000, 0.923077, 0.907692, 0.892308, 0.876923, 0.861538, 0.846154, 0.830769, 0.815385, 0.800000, 0.784615],
        [0.000000, 0.769231, 0.753846, 0.738462, 0.723077, 0.707692]]

    net = PolyNet(
        two_way_scales=two_way_scales,
        poly_scales=poly_scales,
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


def polynet(**kwargs):
    """
    PolyNet model from 'PolyNet: A Pursuit of Structural Diversity in Very Deep Networks,'
    https://arxiv.org/abs/1611.05725.

    Parameters:
    ----------
    pretrained : bool, default False
        Whether to load the pretrained weights for model.
    ctx : Context, default CPU
        The context in which to load the pretrained weights.
    root : str, default '~/.mxnet/models'
        Location for keeping the model parameters.
    """
    return get_polynet(model_name="polynet", **kwargs)


def _test():
    import numpy as np
    import mxnet as mx

    pretrained = False

    models = [
        polynet,
    ]

    for model in models:

        net = model(pretrained=pretrained)

        ctx = mx.cpu()
        if not pretrained:
            net.initialize(ctx=ctx)

        net_params = net.collect_params()
        weight_count = 0
        for param in net_params.values():
            if (param.shape is None) or (not param._differentiable):
                continue
            weight_count += np.prod(param.shape)
        print("m={}, {}".format(model.__name__, weight_count))
        assert (model != polynet or weight_count == 95366600)

        x = mx.nd.zeros((1, 3, 331, 331), ctx=ctx)
        y = net(x)
        assert (y.shape == (1, 1000))


if __name__ == "__main__":
    _test()
