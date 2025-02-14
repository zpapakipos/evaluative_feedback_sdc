import constants as c
import tensorflow as tf
import numpy as np


def conv_layers(scope_name, inpt, channel_sizes, kernels, strides):
    """ Makes arbitrary convolutional layers on top of given layer. Returns
        flattened result (ready for FC & output layers).

        :param scope_name: The variable scope name for the conv layers
        :param inpt: The existing layer to build on top of
        :param channel_sizes: The desired number of channels after each conv layer
        :param kernels: The kernel for each conv layer
        :param strides: The stried for each conv layer

        :return: Flattened resulting tensor after new conv layers
    """
    with tf.variable_scope(scope_name, reuse=False):
        conv_tensor = inpt
        for channels, kernel_len, stride_len in zip(channel_sizes, kernels, strides):
            kernel = (kernel_len, kernel_len)
            stride = (1, stride_len, stride_len, 1)
            conv_tensor = tf.layers.conv2d(conv_tensor, filters=channels,
                                           kernel_size=kernel,
                                           strides=stride, padding=c.PADDING,
                                           activation=tf.nn.relu,
                                           name="%dx%d" % (kernel_len, kernel_len))
        conv_shape = conv_tensor.shape
        out_sz = conv_shape[1].value*conv_shape[2].value*conv_shape[3].value
        flattened_conv = tf.reshape(conv_tensor, shape=[-1, out_sz],
                                    name="flattened")
    return flattened_conv


def fc_layers(scope_name, inpt, fc_sizes, additional_input=None):
    """ Makes arbitrary fully-connected layers on top of given layer. Returns
        resulting tensor.

        :param scope_name: The variable scope name for the FC layers
        :param inpt: The existing layer to build on top of
        :param channel_sizes: The desired number of channels after each FC layer
        :param additional_input: A tuple of (tensor, i) where tensor contains additonal values that
                                 should be concatenated after the ith fully connected layer

        :return: The resulting tensor after new FC layers
    """
    with tf.variable_scope(scope_name, reuse=False):
        fc_layer = inpt
        for i, sz in enumerate(fc_sizes):
            #make fully connected later
            fc_layer = tf.layers.dense(fc_layer, sz, name='fc_%d' % i,
                                        activation=tf.nn.relu)
            #concat additional input onto this layer if necessary
            if additional_input and additional_input[1] == i:
                to_concat = tf.expand_dims(additional_input[0], 1)
                fc_layer = tf.concat([fc_layer, to_concat], axis=1)

    return fc_layer


def gen_batches(tup, shuffle=True, batch_sz=c.BATCH_SIZE, only_positive=False):
    """ Returns a generator of batches, given data.

        :param tup: All the data to return in batches; tuple of
                    (images, labels, feedback)
        :param suffle: whether to shuffle the data first
        :param only_positive: if true, only examples with positive feedback will be included

        :return: A generator of batches, each represented as a tuple of
                 (images, labels, feedback)
    """
    imgs, labels, feedback = tup
    #shuffle or leave in order (shuffle indicies since multiple copies of dataset will not fit in mem)
    indicies = np.where(feedback>0.0)[0] if only_positive else np.array(range(len(imgs)))
    if shuffle:
        np.random.shuffle(indicies)
    #make batches
    for s in range(0, len(indicies), batch_sz):
        e = s + batch_sz
        batch_indices = indicies[s:e]
        yield imgs[batch_indices], labels[batch_indices], feedback[batch_indices]
