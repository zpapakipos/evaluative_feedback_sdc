from tensorflow.python.platform import gfile
import numpy as np, tensorflow as tf
import constants as c
import utils, os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

class Model:
    def __init__(self):
        """ Loads a pre-trained Inception net, adds desired layers, and 
            initializes it for training/evaluation. Or loads in an existing 
            re-trained model, if one exists.

            :param sess: A Tensorflow session
        """
        self.sess = tf.Session()
        self._define_graph()

        self.saver = tf.train.Saver()
        self.summary_writer = tf.summary.FileWriter(c.F_SUMMARY_DIR, self.sess.graph)

        #self.sess.run(tf.global_variables_initializer())
        self.sess.run(tf.variables_initializer(self.new_vars)) #only init new vars
        self._load_model_if_exists()

    def _define_graph(self):
        """ Loads in the Inception net and adds desired layers. """
        self._add_image_processing()
        self._create_inception_tensor()
        with tf.variable_scope('new_vars'):
            self._add_retrain_ops()
            self.new_vars = tf.global_variables(scope=tf.get_variable_scope().name)

    def _add_image_processing(self):
        """ Makes a placeholder for raw images and processes them into a new tensor. """
        self.raw_img_input = tf.placeholder(tf.float32, name='raw_image_input')
        resize_shape = tf.stack([c.INPUT_HEIGHT, c.INPUT_WIDTH])
        resize_shape_as_int = tf.cast(resize_shape, dtype=tf.int32)
        resized_image = tf.image.resize_bilinear(self.raw_img_input, resize_shape_as_int)
        offset_image = tf.subtract(resized_image, c.INPUT_MEAN)
        self.processed_images = tf.multiply(offset_image, 1.0 / c.INPUT_STD)

    def _create_inception_tensor(self):
        """ Loads in the Inception net, saving the desired input & bottleneck 
            tensors as insta
            nce variables. Adds a stop gradient to the bottleneck 
            tensor. """
        #redifine the input to have any batch size
        self.img_input = tf.placeholder(tf.float32, [None, c.INPUT_HEIGHT, c.INPUT_WIDTH, c.INPUT_DEPTH], name=c.IMAGE_INPUT_TENSOR_NAME)
        
        print('Loading Inception model at path: ', c.INCEPTION_PATH)
        with gfile.FastGFile(c.INCEPTION_PATH, 'rb') as f:
            graph_def = tf.GraphDef()
            graph_def.ParseFromString(f.read())
            self.bottleneck_tensor = (tf.import_graph_def(
                graph_def,
                name='',
                input_map={c.IMAGE_INPUT_TENSOR_NAME: self.img_input},
                return_elements=[
                    c.BOTTLENECK_TENSOR_NAME#,
                    #c.IMAGE_INPUT_TENSOR_NAME
                ]))

        # make everything before chosen bottleneck tensor untrainable
        self.bottleneck_tensor = tf.stop_gradient(self.bottleneck_tensor, name="bottleneck_stop_gradient")
        self.bottleneck_tensor = tf.squeeze(self.bottleneck_tensor, [0]) #there is extra dim of size 1 in their code

    def _add_retrain_ops(self):
        """ Adds new layers (specified in constants.py), loss, & train op to graph. """
        self.global_step = tf.Variable(0, name="global_step", trainable=False)
        self.labels = tf.placeholder(tf.float32, [None], name='labels')
        self.feedback = tf.placeholder(tf.float32, [None], name='human_feedback')

        with tf.name_scope('new_layers'):
            flattened_conv = utils.conv_layers("conv", self.bottleneck_tensor,
                                               c.CONV_CHANNELS, c.CONV_KERNELS,
                                               c.CONV_STRIDES)

            fc_output = utils.fc_layers("fc", flattened_conv, c.FC_CHANNELS, additional_input=(self.labels,0))  ##changed from p_net                   
    
            self.feedback_predictions = tf.layers.dense(fc_output, 1, name='feedback_predictions')
            self.feedback_predictions = tf.tanh(self.feedback_predictions) #restrict to -1 to 1 
            self.feedback_predictions = tf.reshape(self.feedback_predictions, [-1])

        with tf.name_scope('loss'):
            self.loss = tf.reduce_mean(tf.square(self.feedback - self.feedback_predictions))                    ##changed from p_net
            self.abs_err = tf.abs(self.feedback - self.feedback_predictions)*c.MAX_ANGLE                        ##changed from p_net
            self.train_loss_summary = tf.summary.scalar('train_loss', self.abs_err)
            self.val_loss_summary = tf.summary.scalar('val_loss', self.abs_err)

        with tf.name_scope('train'):
            optimizer = tf.train.AdamOptimizer(c.LRATE)
            self.train_op = optimizer.minimize(self.loss, global_step=self.global_step)

    def _load_model_if_exists(self):
        """ Loads an existing pre-trained model from the model directory, if one exists. """
        check_point = tf.train.get_checkpoint_state(c.F_MODEL_DIR)
        if check_point and check_point.model_checkpoint_path:
            print 'Restoring model from ' + check_point.model_checkpoint_path
            self.saver.restore(self.sess, check_point.model_checkpoint_path)

    def _process_images(self, img_batch):
        """ Turns raw images into processed images by running them through the graph.

        :param img_batch: The raw images to process

        :return: The processed images
        """
        return self.sess.run(self.processed_images, feed_dict={self.raw_img_input: img_batch})

    def _save(self):
        """ Saves the model
        """
        self.saver.save(self.sess, c.F_MODEL_PATH, global_step=self.global_step)

    def _train_step(self, img_batch, label_batch, feedback_batch):
        """ Executes a training step on a given training batch. Runs the train op 
            on the given batch and regularly writes out training loss summaries 
            and saves the model.

            :param img_batch: The batch images
            :param label_batch: The batch labels
            :param feedback_batch: The batch human feedback
        """
        processed_images = self._process_images(img_batch)
        sess_args = [self.global_step, self.train_loss_summary, self.feedback_predictions, self.abs_err, self.train_op]
        feed_dict = {self.img_input: processed_images,
                     self.labels: label_batch,
                     self.feedback: feedback_batch}
        step, loss_summary, feedback_predictions, abs_err, _ = self.sess.run(sess_args, feed_dict=feed_dict)

        if (step - 1) % c.SUMMARY_SAVE_FREQ == 0:
            self.summary_writer.add_summary(loss_summary, global_step=step)

        if (step - 1) % c.MODEL_SAVE_FREQ == 0:
            self._save()

        print ""
        print "Completed step:", step
        print "Training loss:", abs_err
        print "Average prediction:", np.mean(feedback_predictions)
        print "First prediction:", feedback_predictions[0]

    def train(self, train_tup, val_tup):
        """ Training loop. Trains & validates for the given number of epochs 
            on given data.
            
            :param train_tup: All the training data; tuple of (images, labels, feedback)
            :param val_tup: All the validation data; tuple of (images, labels, feedback)
        """
        for i in xrange(c.NUM_EPOCHS):
            print "\nEpoch", i+1, "("+str(len(train_tup[0])/c.BATCH_SIZE)+" steps)"
            for imgs, labels, feedback in utils.gen_batches(train_tup):
                self._train_step(imgs, labels, feedback)
            self._save()
            self.eval(val_tup)

                                                                                                        ##changed from p_net
    def eval(self, val_tup):
        """ Evaluates the model on given data. Specifically, the angle that maximizes feedbacl.
            Writes out a validation loss summary.

            :param val_tup: The data to evaluate the model on; tuple of (images, labels, feedback)
        """
        #get data
        imgs, labels, _ = val_tup
        processed_imgs = self._process_images(imgs)
        feedbacks = [] #rows are all same angle, col is all same img

        #try all potential angles
        for potential_angle in c.DISCRETE_ANGLES:
            angle_labels = [potential_angle for _ in xrange(len(imgs))]
            angle_feedback = sess.run([feedback_predictions], feed_dict={self.img_input: processed_imgs, self.labels: angle_labels})
            feedbacks.append(angle_feedback)

        #convert feebacks to numpy and get row that maximizes each column
        best_angle_numbers = np.argmax(np.array(feedbacks), axis=0)
        angle_predictions = np.array([c.DISCRETE_ANGLES[num] for num in best_angle_numbers])
        abs_err = np.mean((angle_predictions-labels)**2)*c.MAX_ANGLE

        #write summary
        loss_summary = tf.Summary(value=[tf.Summary.Value(tag="val_loss", simple_value=abs_err)])
        self.summary_writer.add_summary(loss_summary, global_step=step)
        
        print ""
        print "Valiation Loss:", abs_err

    def eval_feedback(self, val_tup):
        """ Evaluates the feedback predictions on given data. Writes out a validation loss summary.

            :param val_tup: The data to evaluate the model on; tuple of (images, labels, feedback)
        """
        imgs, angles, feedback = val_tup
        processed_imgs = self._process_images(imgs)
        sess_args = [self.global_step, self.val_loss_summary, self.abs_err]
        feed_dict = {self.img_input: processed_imgs,
                     self.labels: angles,
                     self.feeback: feedback}
        step, loss_summary, abs_err = self.sess.run(sess_args, feed_dict=feed_dict)

        


