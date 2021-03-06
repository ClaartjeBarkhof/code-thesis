import torch as torch
import transformers
from torch.utils.data import DataLoader
from transformers import RobertaTokenizerFast, logging as transformers_logging  # type: ignore
from datasets import load_dataset, list_datasets, load_from_disk, ReadInstruction  # type: ignore
from typing import List, Dict, Union, Optional
from collections import OrderedDict
import os
import pathlib

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# transformers.logging.set_verbosity_error()


class NewsData:
    """
    A class to handle news data preparation, downloading and loading.
    """
    def __init__(self, dataset_name: str, tokenizer_name: str,
                 batch_size: int = 8, num_workers: int = 4,
                 pin_memory: bool = True, max_seq_len: int = 64,
                 device="cuda:0"):

        # DATA DIRECTORY
        dataset_list = ["cnn_dailymail", "ptb_text_only", "tom_ptb", "wikipedia", "yelp", "optimus_yelp"]
        assert dataset_name in dataset_list, f"Make sure the data set exists, choices: {dataset_list}"

        self.device = device

        # FOR GPU USE
        self.pin_memory = pin_memory

        self.max_seq_len = max_seq_len

        # DATASET PROPERTIES
        self.dataset_name = dataset_name
        self.batch_size = batch_size
        self.tokenizer_name = tokenizer_name
        self.num_workers = num_workers

        self.datasets = {}
        self.encoded_datasets = {}

        # TOKENIZER
        self.tokenizer = RobertaTokenizerFast.from_pretrained('roberta-base')

        name = '3.0.0' if self.dataset_name == 'cnn_dailymail' else None
        # assert self.dataset_name in list_datasets(), "Currently only supporting datasets from Huggingface"

        path_to_file = pathlib.Path(__file__).parent.absolute()
        # debug_ext = "[:{}]".format(debug_data_len) if debug else ""
        data_path = "{}/NewsData/{}-{}-seqlen{}".format(path_to_file, self.dataset_name, self.tokenizer_name, max_seq_len)

        if os.path.isdir(data_path):
            print("Is file!")
            for split in ['train', 'validation', 'test']:
                self.datasets[split] = load_from_disk(data_path+"/"+split)
                print(split, len(self.datasets[split]))
        else:
            print("New pre-processing")
            if dataset_name in ["ptb_text_only", "cnn_dailymail"]:
                for split in ['train', 'validation', 'test']:
                    self.datasets[split] = load_dataset(self.dataset_name, name=name, ignore_verifications=True, split=split)
            elif dataset_name == "tom_ptb":
                self.datasets = load_dataset("text", data_files=dict(
                    train= f"/home/cbarkhof/code-thesis/NewsVAE/NewsData/tom_ptb/train_repreprocessed.txt",
                    validation= f"/home/cbarkhof/code-thesis/NewsVAE/NewsData/tom_ptb/valid_repreprocessed.txt",
                    test= f"/home/cbarkhof/code-thesis/NewsVAE/NewsData/tom_ptb/test_repreprocessed.txt",
                ))
            elif dataset_name == "wikipedia":
                splits = [0, 70, 85, 100] # make train 70%, valid 15%, test 15% split from the train split
                datasets = load_dataset("wikipedia", "20200501.en",
                                        split=[ReadInstruction('train', from_=splits[i], to=splits[i + 1],
                                                               unit='%') for i in range(3)])
                self.datasets = {"train": datasets[0], "validation": datasets[1], "test": datasets[2]}
                print(type(self.datasets["train"]))
            elif dataset_name == "yelp":
                splits = [0, 50, 100] # split test in validation and test
                s = ["train"] + [ReadInstruction('test', from_=splits[i], to=splits[i + 1], unit='%') for i in range(2)]
                datasets = load_dataset("yelp_review_full", split=s)
                self.datasets = {"train": datasets[0], "validation": datasets[1], "test": datasets[2]}
            elif dataset_name == "optimus_yelp":
                if os.path.isfile("/home/cbarkhof/code-thesis/NewsVAE/NewsData/optimus_yelp/train.csv"):
                    self.datasets = load_dataset("csv", data_files=dict(
                        train=f"/home/cbarkhof/code-thesis/NewsVAE/NewsData/optimus_yelp/train.csv",
                        validation=f"/home/cbarkhof/code-thesis/NewsVAE/NewsData/optimus_yelp/valid.csv",
                        test=f"/home/cbarkhof/code-thesis/NewsVAE/NewsData/optimus_yelp/test.csv",
                    ))
                else:
                    # /Users/claartje/Dropbox/Studie/Master AI/Thesis/code-thesis/NewsVAE/NewsData
                    self.datasets = load_dataset("csv", data_files=dict(
                        train=f"/Users/claartje/Dropbox/Studie/Master AI/Thesis/code-thesis/NewsVAE/NewsData/optimus_yelp/train.csv",
                        validation=f"/Users/claartje/Dropbox/Studie/Master AI/Thesis/code-thesis/NewsVAE/NewsData/optimus_yelp/valid.csv",
                        test=f"/Users/claartje/Dropbox/Studie/Master AI/Thesis/code-thesis/NewsVAE/NewsData/optimus_yelp/test.csv",
                    ))
            for split in ['train', 'validation', 'test']:
                self.datasets[split] = self.datasets[split].map(self.convert_to_features, batched=True)
                columns = ['attention_mask', 'input_ids']

                self.datasets[split].set_format(type='torch', columns=columns)

                if self.dataset_name in ["wikipedia", "yelp"]:
                    self.datasets[split].__dict__["_split"] = split  # to bypass a bug in save_to_disk
                self.datasets[split].save_to_disk(data_path+"/"+split)

                print(f"Saved split {split} in {data_path+'/'+split}")

    def train_dataloader(self):
        train_loader = DataLoader(self.datasets['train'], collate_fn=self.collate_fn,
                                  batch_size=self.batch_size, num_workers=self.num_workers,
                                  pin_memory=self.pin_memory)
        return train_loader

    def val_dataloader(self, shuffle=False, batch_size=None):
        if batch_size is not None:
            bs = batch_size
        else:
            bs = self.batch_size
        val_loader = DataLoader(self.datasets['validation'], collate_fn=self.collate_fn,
                                batch_size=bs, num_workers=self.num_workers,
                                pin_memory=self.pin_memory, shuffle=shuffle)
        return val_loader

    def test_dataloader(self):
        test_loader = DataLoader(self.datasets['test'], collate_fn=self.collate_fn,
                                 batch_size=self.batch_size, num_workers=self.num_workers,
                                 pin_memory=self.pin_memory)
        return test_loader

    def collate_fn(self, examples):
        """
        A function that assembles a batch. This is where padding is done, since it depends on
        the maximum sequence length in the batch.

        :param examples: list of truncated, tokenised & encoded sequences
        :return: padded_batch (batch x max_seq_len)
        """

        # Get rid of text and label data, just
        examples = [{"attention_mask": e["attention_mask"], "input_ids":e["input_ids"]} for e in examples]

        # Combine the tensors into a padded batch
        padded_batch = self.tokenizer.pad(examples, return_tensors='pt', padding=True,
                                          max_length=self.max_seq_len,
                                          return_attention_mask=True)

        return padded_batch

    def convert_to_features(self, data_batch: OrderedDict) -> OrderedDict:
        """
        Truncates and tokenises & encodes a batch of text samples.

        ->  Note: does not pad yet, this will be done in the DataLoader to allow flexible
            padding according to the longest sequence in the batch.

        :param data_batch: batch of text samples
        :return: encoded_batch: batch of samples with the encodings with the defined tokenizer added
        """

        if self.dataset_name == "cnn_dailymail":
            key = "article"
        elif self.dataset_name == "tom_ptb" or self.dataset_name == "wikipedia" \
                or self.dataset_name == "yelp" or self.dataset_name == "optimus_yelp":
            key = "text"
        else:
            key = "sentence"


        print("convert to features")
        encoded_batch = self.tokenizer(data_batch[key], truncation=True, max_length=self.max_seq_len)

        return encoded_batch


if __name__ == "__main__":
    print("-> Begin!")
    data = NewsData('optimus_yelp', 'roberta', max_seq_len=64)
    print("-> End!")

    print(data.datasets['train'].shape)
    print(data.datasets['validation'].shape)
    print(data.datasets['test'].shape)
