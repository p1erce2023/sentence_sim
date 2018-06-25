# -*- coding: utf-8 -*-
from gensim.models import KeyedVectors
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import train_test_split, GridSearchCV
import click
import numpy as np
import pandas as pd


TEST_SIZE = 22000
logistic_params = [
    {'C': [0.05, 0.2, 1]}
]


def get_ids(qids):
    ids = []
    for t_ in qids:
        ids.append(int(t_[1:]))
    return np.asarray(ids)


def get_texts(file_path, question_path):
    qes = pd.read_csv(question_path)
    file = pd.read_csv(file_path)
    q1id, q2id = file['q1'], file['q2']
    id1s, id2s = get_ids(q1id), get_ids(q2id)
    texts = []
    for t_ in zip(id1s, id2s):
        texts.append((
            qes['words'][t_[0]], qes['words'][t_[1]],
            qes['chars'][t_[0]], qes['chars'][t_[1]]
        ))
    return texts


def make_submission(predict_prob):
    with open('submission.csv', 'w') as file:
        file.write(str('y_pre') + '\n')
        for line in predict_prob:
            file.write(str(line) + '\n')
    file.close()


TRAIN_PATH = 'mojing/train.csv'
TEST_PATH = 'mojing/test.csv'
QUESTION_PATH = 'mojing/question.csv'

print('Load files...')
questions = pd.read_csv(QUESTION_PATH)
train = pd.read_csv(TRAIN_PATH)
test = pd.read_csv(TEST_PATH)
model_w2v = KeyedVectors.load_word2vec_format('mojing/word_embed.txt')
model_c2v = KeyedVectors.load_word2vec_format('mojing/char_embed.txt')

print('Fit the corpus...')
tfidf_w, tfidf_c = TfidfVectorizer(), TfidfVectorizer()
tfidf_w.fit(questions['words'])
tfidf_c.fit(questions['chars'])

print('Get texts...')
train_texts = get_texts(TRAIN_PATH, QUESTION_PATH)
test_texts = get_texts(TEST_PATH, QUESTION_PATH)

print('Generate features...')


def get_features(sentences):
    return_features = []
    for w1, w2, c1, c2 in sentences:
        futures = {}
        vw1 = [model_w2v.get_vector(w) for w in w1.split()]
        vw2 = [model_w2v.get_vector(w) for w in w2.split()]
        vc1 = [model_c2v.get_vector(c) for c in c1.split()]
        vc2 = [model_c2v.get_vector(c) for c in c2.split()]
        nvw1 = [v / np.linalg.norm(v) for v in vw1]
        nvw2 = [v / np.linalg.norm(v) for v in vw2]
        nvc1 = [v / np.linalg.norm(v) for v in vc1]
        nvc2 = [v / np.linalg.norm(v) for v in vc2]

        # raw features, vsm with tf-idf
        both_w = tfidf_w.transform([w1, w2]).toarray()
        futures['w_dist'] = np.linalg.norm(both_w[0] - both_w[1])
        both_c = tfidf_c.transform([c1, c2]).toarray()
        futures['c_dist'] = np.linalg.norm(both_c[0] - both_c[1])

        # word vector features
        vw1_aver = np.average(vw1, axis=0)
        vw2_aver = np.average(vw2, axis=0)
        futures['word_average_dist'] = np.linalg.norm(vw1_aver - vw2_aver)

        vw1_max = np.max(vw1, axis=0)
        vw2_max = np.max(vw2, axis=0)
        futures['word_max_dist'] = np.linalg.norm(vw1_max - vw2_max)

        nvw1_aver = np.average(nvw1, axis=0)
        nvw2_aver = np.average(nvw2, axis=0)
        futures['norm_word_average_cos'] = np.dot(nvw1_aver, nvw2_aver)

        nvw1_max = np.max(nvw1, axis=0)
        nvw2_max = np.max(nvw2, axis=0)
        futures['norm_word_max_cos'] = np.dot(nvw1_max, nvw2_max)

        # char vector features
        vc1_aver = np.average(vc1, axis=0)
        vc2_aver = np.average(vc2, axis=0)
        futures['char_average_dist'] = np.linalg.norm(vc1_aver - vc2_aver)

        vc1_max = np.max(vc1, axis=0)
        vc2_max = np.max(vc2, axis=0)
        futures['char_max_dist'] = np.linalg.norm(vc1_max - vc2_max)

        nvc1_aver = np.average(nvc1, axis=0)
        nvc2_aver = np.average(nvc2, axis=0)
        futures['norm_char_average_cos'] = np.dot(nvc1_aver, nvc2_aver)

        nvc1_max = np.max(nvc1, axis=0)
        nvc2_max = np.max(nvc2, axis=0)
        futures['norm_char_max_cos'] = np.dot(nvc1_max, nvc2_max)

        # sentence vector features
        # todo

        return_features.append(futures)
    return return_features


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.option("-c", "--cross_validate", type=int, default=5,
              help="Set the cross-validation number.")
@click.option("-j", "--jobs", type=int, default=1,
              help="Set the number of parallel jobs.")
def main(cross_validate, jobs):
    features_train = get_features(train_texts)
    features_test = get_features(test_texts)

    print('Transforming feature to matrices...')
    vectorizer = DictVectorizer()
    X_all = vectorizer.fit_transform(features_train)
    print('Split dev from train...')
    X, X_dev, Y, Y_dev = train_test_split(X_all, train['label'], test_size=TEST_SIZE, shuffle=False)

    print('Train classifier...')
    grid = GridSearchCV(LogisticRegression(tol=1e-6, class_weight="balanced"), logistic_params,
                        n_jobs=jobs, cv=cross_validate, verbose=1)
    grid.fit(X, Y)

    print('Predict dev...')
    Y_pred_dev = grid.best_estimator_.predict_proba(X_dev)
    print('Dev log_loss', log_loss(Y_dev, Y_pred_dev, eps=1e-15))

    print('Train on all and predict test...')
    grid = GridSearchCV(LogisticRegression(tol=1e-6, class_weight="balanced"), logistic_params,
                        n_jobs=jobs, cv=cross_validate, verbose=1)
    grid.fit(X_all, train['label'])
    pred = grid.best_estimator_.predict_proba(vectorizer.transform(features_test))
    make_submission(pred[:, 1])

    print('Complete')


if __name__ == '__main__':
    main()