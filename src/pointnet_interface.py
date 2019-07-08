import tensorflow as tf
import numpy as np
import importlib
import sys

class PointNetInterface:
    def __init__(self, max_points, fft = False, sink = False):
        checkpoint_path = "pointnet/log/model.ckpt"

        sys.path.append("pointnet/models")
        model = importlib.import_module("pointnet_cls")

        self.x_pl, self.y_pl = model.placeholder_inputs(1, max_points)
        self.is_training = tf.placeholder(tf.bool, shape = ())

        with tf.variable_scope(tf.get_variable_scope(), reuse = tf.AUTO_REUSE):
            logits, end_points = model.get_model(self.x_pl, self.is_training)

        self.y_pred = tf.nn.softmax(logits)
        loss = model.get_loss(logits, self.y_pl, end_points)
        self.grad_loss_wrt_x = tf.gradients(loss, self.x_pl)[0]

        self.grad_out_wrt_x = []

        for i in range(40):
            self.grad_out_wrt_x.append(tf.gradients(logits[:, i], self.x_pl)[0])

        if fft:
            self.x_freq = tf.placeholder(tf.complex64, shape = self.x_pl.shape.as_list())
            self.x_time = tf.real(tf.ifft2d(self.x_freq))

            with tf.variable_scope(tf.get_variable_scope(), reuse = tf.AUTO_REUSE):
                logits, end_points = model.get_model(self.x_time, self.is_training)

            loss = model.get_loss(logits, self.y_pl, end_points)
            self.grad_loss_wrt_x_freq = tf.gradients(loss, self.x_freq)[0]

        if sink:
            self.x_clean = tf.placeholder(tf.float32, shape = self.x_pl.shape.as_list())
            self.sinks = tf.placeholder(tf.float32, shape = (1, None, 3))
            self.sink_coeff = tf.placeholder(tf.float32, shape = (1, None))
            self.epsilon = tf.placeholder(tf.float32, shape = ())

            x_to_sinks = sinks[:, :, tf.newaxis, :] - x_clean[:, tf.newaxis, :, :]
            dist = tf.linalg.norm(x_to_sinks, axis = 3)
            sink_power = tf.tanh(self.sink_coeff)[:, :, tf.newaxis, tf.newaxis]
            rbf = tf.exp(-((dist / epsilon) ** 2))[:, :, :, tf.newaxis]
            perturb = sink_power * rbf * x_to_sinks / dist[:, :, :, tf.newaxis]
            perturb = tf.where(tf.is_finite(perturb), perturb, tf.zeros_like(perturb))
            self.x_perturb = self.x_clean + tf.sum(perturb, axis = 1)

            with tf.variable_scope(tf.get_variable_scope(), reuse = tf.AUTO_REUSE):
                logits, end_points = model.get_model(self.x_perturb, self.is_training)

            loss = model.get_loss(logits, self.y_pl, end_points)
            self.grad_loss_wrt_sink_coeff = tf.gradients(loss, self.sink_coeff)[0]

        # load saved parameters
        saver = tf.train.Saver()
        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        config.log_device_placement = True
        self.sess = tf.Session(config = config)
        saver.restore(self.sess, checkpoint_path)
        print("Model restored!")

    def clean_up(self):
        self.sess.close()

    def pred_fn(self, x):
        return self.sess.run(self.y_pred, feed_dict = {self.x_pl: [x], self.is_training: False})[0]

    def x_perturb_sink_fn(self, x, sinks, sink_coeff, epsilon):
        return self.sess.run(self.x_perturb, feed_dict = {self.x_clean: [x], self.sinks: [sinks], self.sink_coeff: [sink_coeff], self.epsilon: epsilon, self.is_training: False})[0]

    def grad_fn(self, x, y):
        return self.sess.run(self.grad_loss_wrt_x, feed_dict = {self.x_pl: [x], self.y_pl: [y], self.is_training: False})[0]

    def grad_freq_fn(self, x, y):
        return self.sess.run(self.grad_loss_wrt_x_freq, feed_dict = {self.x_freq: [x], self.y_pl: [y], self.is_training: False})[0]

    def grad_sink_fn(self, x, y, sinks, sink_coeff, epsilon):
        return self.sess.run(self.grad_loss_wrt_sink_coeff, feed_dict = {self.x_clean: [x], self.y_pl: [y], self.sinks: [sinks], self.sink_coeff: [sink_coeff], self.epsilon: epsilon, self.is_training: False})[0]

    def output_grad_fn(self, x):
        res = []

        for i in range(len(self.grad_out_wrt_x)):
            res.append(self.sess.run(self.grad_out_wrt_x[i], feed_dict = {self.x_pl: [x], self.is_training: False})[0])

        return np.array(res)
