"""Utils for loading and adding annotations to the data"""
import ast
import logging
import msgpack
import os
import pandas as pd
from functools import lru_cache
from spacy.tokens import Doc
from tqdm import tqdm

from src import HOME_DIR
from src.utils.spacy import nlp, apply_extensions

logger = logging.getLogger(__name__)
cache = lru_cache(maxsize=None)


def _load_spacy():
    """Loads serialized spacy vocab and docs

    Returns
    -------
    dict
        Maps doc id to bytes for spacy doc.
    """
    spacy_path = os.path.join(HOME_DIR, 'data/processed/spacy')
    if os.path.exists(spacy_path):
        with open(spacy_path, 'rb') as f:
            m = msgpack.load(f)
        nlp.vocab.from_bytes(m[b'vocab'])
        return m[b'docs']
    else:
        logger.warn('No serialized Spacy found')
        return None


class Paragraph:
    """A paragraph from the corpus

    Parameters
    ----------
    row : pd.Series
        The row of data referring to this speech.
    parent : src.corpus.Speech
        A reference to the Speech object that contains this paragraph.
    """
    def __init__(self, row, parent):
        self.index = row.paragraph_index
        self.id_ = row.paragraph_id
        self.row = row
        self.speech = parent

    def spacy_doc(self):
        return self.speech.spacy_paragraphs()[self.id_]

    def session(self):
        return self.row.session

    def year(self):
        return self.row.year

    def country_code(self):
        return self.row.country

    def country(self):
        return self.row.country_name

class Speech:
    """A speech from the corpus

    Serialized Spacy docs are lazy loaded.

    Parameters
    ----------
    group : pd.DataFrame
        The subset of rows/paragraphs that belong to this speech.
    spacy_bytes : bytes
        Serialized spacy doc.
    """
    def __init__(self, group, spacy_bytes=None):
        self.id_ = group.document_id.unique()[0]
        self._spacy_bytes = spacy_bytes
        self.group = group
        self.paragraphs = [
            Paragraph(row, self)
            for _, row in group.iterrows()
        ]

    @cache
    def spacy_doc(self):
        if self._spacy_bytes is not None:
            doc = apply_extensions(Doc(nlp.vocab).from_bytes(self._spacy_bytes))
            return doc
        else:
            raise FileNotFoundError('No serialized Spacy found')

    def spacy_paragraphs(self):
        return {par._.id: par for par in self.spacy_doc()._.paragraphs}

    def session(self):
        return self.group.session.iloc[0]

    def year(self):
        return self.group.year.iloc[0]

    def country_code(self):
        return self.group.country.iloc[0]

    def country(self):
        return self.group.country_name.iloc[0]

class Corpus:
    """UN General Debate Corpus"""
    def __init__(self, filename='data/processed/debates_paragraphs.csv'):
        self.filename = filename
        self._load(filename)

    def _load(self, filename):
        debates = pd.read_csv(
            os.path.join(HOME_DIR, filename), dtype={'paragraph_id': str})
        debates.bag_of_words = debates.bag_of_words.apply(ast.literal_eval)
        spacy = _load_spacy()
        self.debates = debates
        self.speeches = [
            Speech(
                group,
                spacy.pop(bytes(str(id_), encoding='utf8')) if spacy else None)
            for id_, group in debates.groupby('document_id')
        ]
        # This list should be ordered exactly the same as the csv.
        self.paragraphs = [par for sp in self.speeches for par in sp.paragraphs]

    def add_dataframe_column(self, column):
        """Add column to the dataframe

        Add a column to the corpus dataframe and save it so that it loads next
        time. Useful for adding paragraph level annotations that don't
        necessarily make sense as a Spacy extension.

        Parameters
        ----------
        column : pd.Series
            New column to append to the corpus dataframe. Should be named.
        """
        self.debates = pd.concat([self.debates, column], axis=1)
        self.debates.to_csv(self.filename, index=False)

    def load_spacy_cache(self):
        """Convenience function for doing all of the spacy loading upfront."""
        for sp in tqdm(self.speeches):
            sp.spacy_doc()
