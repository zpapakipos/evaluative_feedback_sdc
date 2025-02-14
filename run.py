
import constants as c

import p_net
import f_net

import sys, os, glob
import numpy as np
import argparse



class Runner:
    def __init__(self, args):
        # read in Data #
        self.train_tup = (None,None,None) #(images,labels,feedbacks)
        self.val_tup = (None,None,None)
        self.read_in_data()

        print("\n\nWound up with:")
        print(len(self.train_tup[0]), "training images")
        print(len(self.val_tup[0]), "validation images\n\n")

        #model
        self.model = p_net.Model() if args.net=="p" else f_net.Model()

    def read_in_data(self):
        print("\nREADING IN DATA...")
        self.train_tup = (np.load(c.TRAIN_DATA_PATH+".npy"),
                          np.load(c.TRAIN_LABELS_PATH+".npy"),
                          np.load(c.TRAIN_FEEDBACK_PATH+".npy"))
        self.val_tup = (np.load(c.VAL_DATA_PATH+".npy"),
                        np.load(c.VAL_LABELS_PATH+".npy"),
                        np.load(c.VAL_FEEDBACK_PATH+".npy"))

    def train(self):
        print("\nTRAINING...")
        self.model.train(self.train_tup, self.val_tup)

    def val(self):
        if not self.model.saved_model_exists():
            print("\n\nNo Model, validating untrained model\n\n")

        print("\nVALIDATING...")
        self.model.eval(self.val_tup)



# helper functions #

def delete_model_files(args):
    model_dir = c.P_MODEL_DIR if args.net=="p" else c.F_MODEL_DIR
    summary_dir = c.P_SUMMARY_DIR if args.net=="p" else c.F_SUMMARY_DIR
    model_files = glob.glob(os.path.join(model_dir, "*"))
    summary_files = glob.glob(os.path.join(summary_dir, "*"))
    for f in model_files+summary_files:
        os.remove(f)

def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--net',
                        help='policy net (p) or feedback net (f)',
                        required=True,
                        choices=['p','f'])

    parser.add_argument('--new',
                        help="Delete old model.",
                        dest='new',
                        action='store_true',
                        default=False)

    parser.add_argument('--val',
                        help="Validate model.",
                        dest='val',
                        action='store_true',
                        default=False)

    parser.add_argument('--train',
                        help="Train model.",
                        dest='train',
                        action='store_true',
                        default=False)

    return parser.parse_args()


# main #

def main():
    args = get_args()

    if args.new:
        #remove all model files
        delete_model_files(args)
    if args.train or args.val:
        runner = Runner(args)

    if args.train:
        runner.train()
    if args.val:
        runner.val()




if __name__ == "__main__":
    main()
