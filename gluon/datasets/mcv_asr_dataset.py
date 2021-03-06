"""
    Mozilla Common Voice ASR dataset.
"""

__all__ = ['McvDataset', 'McvMetaInfo']

import os
import re
import numpy as np
import pandas as pd
from .dataset_metainfo import DatasetMetaInfo
from .asr_dataset import AsrDataset, asr_test_transform


class McvDataset(AsrDataset):
    """
    Mozilla Common Voice dataset for Automatic Speech Recognition (ASR).

    Parameters:
    ----------
    root : str, default '~/.torch/datasets/mcv'
        Path to the folder stored the dataset.
    mode : str, default 'test'
        'train', 'val', 'test', or 'demo'.
    lang : str, default 'en'
        Language.
    subset : str, default 'dev'
        Data subset.
    transform : function, default None
        A function that takes data and transforms it.
    """
    def __init__(self,
                 root=os.path.join("~", ".torch", "datasets", "mcv"),
                 mode="test",
                 lang="en",
                 subset="dev",
                 transform=None):
        super(McvDataset, self).__init__(
            root=root,
            mode=mode,
            transform=transform)
        assert (lang in ("en", "fr", "de", "it", "es", "ca", "pl", "ru", "ru34"))
        self.vocabulary = self.get_vocabulary_for_lang(lang=lang)

        desired_audio_sample_rate = 16000
        vocabulary_dict = {c: i for i, c in enumerate(self.vocabulary)}

        import soundfile
        import librosa
        from librosa.core import resample as lr_resample
        import unicodedata
        import unidecode

        root_dir_path = os.path.expanduser(root)
        assert os.path.exists(root_dir_path)

        lang_ = lang if lang != "ru34" else "ru"
        data_dir_path = os.path.join(root_dir_path, lang_)
        assert os.path.exists(data_dir_path)

        metainfo_file_path = os.path.join(data_dir_path, subset + ".tsv")
        assert os.path.exists(metainfo_file_path)
        metainfo_df = pd.read_csv(
            metainfo_file_path,
            sep="\t",
            header=0,
            index_col=False)
        metainfo_df = metainfo_df[["path", "sentence"]]
        self.data_paths = metainfo_df["path"].values
        self.data_sentences = metainfo_df["sentence"].values

        clips_dir_path = os.path.join(data_dir_path, "clips")
        assert os.path.exists(clips_dir_path)

        for clip_file_name, sentence in zip(self.data_paths, self.data_sentences):
            mp3_file_path = os.path.join(clips_dir_path, clip_file_name)
            assert os.path.exists(mp3_file_path)
            wav_file_name = clip_file_name.replace(".mp3", ".wav")
            wav_file_path = os.path.join(clips_dir_path, wav_file_name)

            # print("==> {}".format(sentence))
            text = sentence.lower()

            if lang == "en":
                text = re.sub("\.|-|???|???", " ", text)
                text = re.sub("&", " and ", text)
                text = re.sub("??", "o", text)
                text = re.sub("??|??", "a", text)
                text = re.sub("??", "e", text)
                text = re.sub(",|;|:|!|\?|\"|???|???|???|???|\(|\)", "", text)
                text = re.sub("\s+", " ", text)
                text = re.sub(" '", " ", text)
                text = re.sub("' ", " ", text)
            elif lang == "fr":
                text = "".join(c for c in text if unicodedata.combining(c) == 0)
                text = re.sub("\.|-|???|???|=|??|\*|???|/|???|_|???", " ", text)
                text = re.sub(",|;|:|!|\?|??|???|???|\"|???|??|??|\(|\)", "", text)
                text = re.sub("???|???|???|???|???|???|\$|??|???|???", "", text)
                text = re.sub("???|??", "'", text)
                text = re.sub("&", " and ", text)
                text = re.sub("??", "oe", text)
                text = re.sub("??", "ae", text)
                text = re.sub("??|??|??|??|??|??|??", "a", text)
                text = re.sub("??|??|??|??|???|??", "o", text)
                text = re.sub("??|??|??", "e", text)
                text = re.sub("??|??", "i", text)
                text = re.sub("??|??", "u", text)
                text = re.sub("??", "y", text)
                text = re.sub("??|??|??|??", "s", text)
                text = re.sub("??|??|??", "z", text)
                text = re.sub("??|??|???", "n", text)
                text = re.sub("??|??", "l", text)
                text = re.sub("??|??", "c", text)
                text = re.sub("??", "ya", text)
                text = re.sub("??", "r", text)
                text = re.sub("??", "d", text)
                text = re.sub("??", "t", text)
                text = re.sub("??", "th", text)
                text = re.sub("??", "g", text)
                text = re.sub("??", "ss", text)
                text = re.sub("??", "mu", text)
                text = re.sub("\s+", " ", text)
            elif lang == "de":
                text = re.sub("\.|-|???|???|/|_|???", " ", text)
                text = re.sub(",|;|:|!|\?|\"|'|???|???|??|??|???|???|???|\"|???|??|??|???|???|\(|\)", "", text)
                text = re.sub("??|???|???|???", "", text)
                text = re.sub("&", " and ", text)
                text = re.sub("??", "a", text)
                text = re.sub("??", "ae", text)
                text = re.sub("??|??|??|??|??|??|??", "a", text)
                text = re.sub("??|??|??|???|??|??|??", "o", text)
                text = re.sub("??|??|??|??|??", "e", text)
                text = re.sub("??|???", "u", text)
                text = re.sub("??|??|??", "i", text)
                text = re.sub("??|??|??|??", "s", text)
                text = re.sub("??|??", "c", text)
                text = re.sub("??", "d", text)
                text = re.sub("??", "g", text)
                text = re.sub("??", "l", text)
                text = re.sub("??", "r", text)
                text = re.sub("??", "n", text)
                text = re.sub("??", "t", text)
                text = re.sub("??|??", "z", text)
                text = re.sub("\s+", " ", text)
            elif lang == "it":
                text = re.sub("\.|-|???|???|/|_|???", " ", text)
                text = re.sub(",|;|:|!|\?|\"|???|???|\"|???|??|??|???|???|<|>|\(|\)", "", text)
                text = re.sub("\$|#|???", "", text)
                text = re.sub("???|`", "'", text)
                text = re.sub("??", "a", text)
                text = "".join((c if c in self.vocabulary else unidecode.unidecode(c)) for c in text)
                text = re.sub("\s+", " ", text)
            elif lang == "es":
                text = re.sub("\.|-|???|???|/|=|_|{|???", " ", text)
                text = re.sub(",|;|:|!|\?|\"|???|???|\"|???|??|??|???|???|<|>|\(|\)|??|??", "", text)
                text = re.sub("???|???", "", text)
                text = "".join((c if c in self.vocabulary else unidecode.unidecode(c)) for c in text)
                text = re.sub("\s+", " ", text)
            elif lang == "ca":
                text = re.sub("\.|-|???|???|/|=|_|??|@|\+|???", " ", text)
                text = re.sub(",|;|:|!|\?|\"|???|???|\"|???|??|??|???|???|<|>|\(|\)|??|??", "", text)
                text = re.sub("???|???", "", text)
                text = "".join((c if c in self.vocabulary else unidecode.unidecode(c)) for c in text)
                text = re.sub("\s+", " ", text)
            elif lang == "pl":
                text = re.sub("\.|-|???|???|/|=|_|??|@|\+|???", " ", text)
                text = re.sub(",|;|:|!|\?|\"|???|???|\"|???|??|??|???|???|<|>|\(|\)", "", text)
                text = re.sub("q", "k", text)
                text = re.sub("x", "ks", text)
                text = re.sub("v", "w", text)
                text = "".join((c if c in self.vocabulary else unidecode.unidecode(c)) for c in text)
                text = re.sub("\s+", " ", text)
            elif lang in ("ru", "ru34"):
                text = re.sub("????-", "????", text)
                text = re.sub("????-", "????", text)
                text = re.sub("-????", "????", text)
                text = re.sub("\.|???|-|???|???|???", " ", text)
                text = re.sub(",|;|:|!|\?|???|???|\"|???|???|??|??|'", "", text)
                text = re.sub("m", "??", text)
                text = re.sub("o", "??", text)
                text = re.sub("z", "??", text)
                text = re.sub("i", "??", text)
                text = re.sub("l", "??", text)
                text = re.sub("a", "??", text)
                text = re.sub("f", "??", text)
                text = re.sub("r", "??", text)
                text = re.sub("e", "??", text)
                text = re.sub("x", "????", text)
                text = re.sub("h", "??", text)
                text = re.sub("\s+", " ", text)
                if lang == "ru34":
                    text = re.sub("??", "??", text)

            text = re.sub(" $", "", text)
            # print("<== {}".format(text))
            text = np.array([vocabulary_dict[c] for c in text], dtype=np.long)
            self.data.append((wav_file_path, text))

            # continue
            if os.path.exists(wav_file_path):
                continue
                # pass
            x, sr = librosa.load(path=mp3_file_path, sr=None)
            if desired_audio_sample_rate != sr:
                y = lr_resample(y=x, orig_sr=sr, target_sr=desired_audio_sample_rate)
                soundfile.write(file=wav_file_path, data=y, samplerate=desired_audio_sample_rate)

    @staticmethod
    def get_vocabulary_for_lang(lang="en"):
        """
        Get the vocabulary for a language.

        Parameters:
        ----------
        lang : str, default 'en'
            Language.

        Returns:
        -------
        list of str
            Vocabulary set.
        """
        assert (lang in ("en", "fr", "de", "it", "es", "ca", "pl", "ru", "ru34"))
        if lang == "en":
            return [' ', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                    't', 'u', 'v', 'w', 'x', 'y', 'z', "'"]
        elif lang == "fr":
            return [' ', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                    't', 'u', 'v', 'w', 'x', 'y', 'z', "'", '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??',
                    '??', '??']
        elif lang == "de":
            return [' ', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                    't', 'u', 'v', 'w', 'x', 'y', 'z', '??', '??', '??', '??']
        elif lang == "it":
            return [' ', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                    't', 'u', 'v', 'w', 'x', 'y', 'z', "'", '??', '??', '??', '??', '??', '??', '??', '??', '??', '??']
        elif lang == "es":
            return [' ', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                    't', 'u', 'v', 'w', 'x', 'y', 'z', "'", '??', '??', '??', '??', '??', '??', '??']
        elif lang == "ca":
            return [' ', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                    't', 'u', 'v', 'w', 'x', 'y', 'z', "'", '??', '??', '??', '??', '??', '??', '??', '??', '??', '??']
        elif lang == "pl":
            return [' ', 'a', '??', 'b', 'c', '??', 'd', 'e', '??', 'f', 'g', 'h', 'i', 'j', 'k', 'l', '??', 'm', 'n', '??',
                    'o', '??', 'p', 'r', 's', '??', 't', 'u', 'w', 'y', 'z', '??', '??']
        elif lang == "ru":
            return [' ', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??',
                    '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??']
        elif lang == "ru34":
            return [' ', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??',
                    '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??', '??']
        else:
            return None


class McvMetaInfo(DatasetMetaInfo):
    def __init__(self):
        super(McvMetaInfo, self).__init__()
        self.label = "MCV"
        self.short_label = "mcv"
        self.root_dir_name = "cv-corpus-6.1-2020-12-11"
        self.dataset_class = McvDataset
        self.lang = "en"
        self.dataset_class_extra_kwargs = {
            "lang": self.lang,
            "subset": "dev"}
        self.ml_type = "asr"
        self.num_classes = None
        self.val_metric_extra_kwargs = [{"vocabulary": None}]
        self.val_metric_capts = ["Val.WER"]
        self.val_metric_names = ["WER"]
        self.test_metric_extra_kwargs = [{"vocabulary": None}]
        self.test_metric_capts = ["Test.WER"]
        self.test_metric_names = ["WER"]
        self.val_transform = asr_test_transform
        self.test_transform = asr_test_transform
        self.saver_acc_ind = 0

    def add_dataset_parser_arguments(self,
                                     parser,
                                     work_dir_path):
        """
        Create python script parameters (for dataset specific metainfo).

        Parameters:
        ----------
        parser : ArgumentParser
            ArgumentParser instance.
        work_dir_path : str
            Path to working directory.
        """
        super(McvMetaInfo, self).add_dataset_parser_arguments(parser, work_dir_path)
        parser.add_argument(
            "--lang",
            type=str,
            default="en",
            help="language")
        parser.add_argument(
            "--subset",
            type=str,
            default="dev",
            help="data subset")

    def update(self,
               args):
        """
        Update dataset metainfo after user customizing.

        Parameters:
        ----------
        args : ArgumentParser
            Main script arguments.
        """
        super(McvMetaInfo, self).update(args)
        self.lang = args.lang
        self.dataset_class_extra_kwargs["lang"] = args.lang
        self.dataset_class_extra_kwargs["subset"] = args.subset

    def update_from_dataset(self,
                            dataset):
        """
        Update dataset metainfo after a dataset class instance creation.

        Parameters:
        ----------
        args : obj
            A dataset class instance.
        """
        vocabulary = dataset._data.vocabulary
        self.num_classes = len(vocabulary) + 1
        self.val_metric_extra_kwargs[0]["vocabulary"] = vocabulary
        self.test_metric_extra_kwargs[0]["vocabulary"] = vocabulary
