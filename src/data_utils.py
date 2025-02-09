import os
import torch
import pickle as pkl
import numpy as np
from torch.utils.data import Dataset
import scipy.sparse as sp
from tqdm import tqdm
from transformers import BertTokenizer, RobertaTokenizer, XLNetTokenizer
import re
from nltk.corpus import stopwords
from multiprocessing import Pool, cpu_count
from tqdm.contrib.concurrent import process_map
# from xclib.data import data_utils as du

cachedStopWords = stopwords.words("english")

def clean_str(string):
    string = string.replace('\n', ' ')
    string = re.sub(r"_", " ", string)
    string = re.sub("\[\d+\]", "", string)
    string = re.sub(r"[^A-Za-z0-9!?\.\'\`]", " ", string)
    # string = ' '.join([word for word in string.split() if word not in cachedStopWords])
    # string = re.sub('(?<=[A-Za-z]),', ' ', string)
    # string = re.sub(r"(),!?", " ", string)
    # string = re.sub(r"[^A-Za-z0-9!?\.\'\`]", " ", string)
    # string = re.sub('(?<=[A-Za-z])\.', '', string)
    # string = re.sub(r'([\d]+)([A-Za-z]+)', '\g<1> \g<2>', string)
    # string = re.sub(r"\'s ", " ", string)
    # string = re.sub(r"s\' ", " ", string)
    string = re.sub(r"\s{2,}", " ", string)
    string = string.strip().lower()
    return string


def get_fast_tokenizer(self):
    if 'roberta' in self.bert_name:
        tokenizer = RobertaTokenizerFast.from_pretrained('roberta-base', do_lower_case=True)
    elif 'xlnet' in self.bert_name:
        tokenizer = XLNetTokenizer.from_pretrained('xlnet-base-cased') 
    else:
        tokenizer = BertWordPieceTokenizer("data/.bert-base-uncased-vocab.txt", lowercase=True)
    return tokenizer

def get_tokenizer(model_name):
    if 'roberta' in model_name:
        print('loading roberta-base tokenizer')
        tokenizer = RobertaTokenizer.from_pretrained('roberta-base', do_lower_case=True)
    elif 'xlnet' in model_name:
        print('loading xlnet-base-cased tokenizer')
        tokenizer = XLNetTokenizer.from_pretrained('xlnet-base-cased')
    else:
        print('loading bert-base-uncased tokenizer')
        tokenizer = BertTokenizer.from_pretrained('bert-base-uncased', do_lower_case=True)
    return tokenizer

def get_inv_prop(dataset, Y):
    if os.path.exists(os.path.join(dataset, 'inv_prop.npy')):
        inv_prop = np.load(os.path.join(dataset, 'inv_prop.npy'))
        return inv_prop

    print("Creating inv_prop file")
    
    A = {'Eurlex': 0.6, 'Amazon-670K': 0.6, 'Amazon-3M': 0.6, 'AmazonCat-13K': 0.55, 'Wiki-500K' : 0.5, 'Wiki10-31K' : 0.55, 'LF-AmazonTitles-131K': 0.6}
    B = {'Eurlex': 2.6, 'Amazon-670K': 2.6, 'Amazon-3M': 2.6, 'AmazonCat-13K': 1.5, 'Wiki-500K': 0.4, 'Wiki10-31K': 1.5, 'LF-AmazonTitles-131K': 2.6}

    d = dataset.split('/')[-1]
    a, b = A[d], B[d]
    
    num_samples = Y.shape[0]
    inv_prop = np.array(Y.sum(axis=0)).ravel()
    
    c = (np.log(num_samples) - 1) * np.power(b+1, a)
    inv_prop = 1 + c * np.power(inv_prop + b, -a)
    
    np.save(os.path.join(dataset, 'inv_prop.npy'), inv_prop)
    return inv_prop

def load_short_data(data_path):

    trn_data, tst_data, lbl_data = [], [], []
    with open(os.path.join(data_path, 'trn.json')) as fin:
        for info in tqdm(fin.readlines(), desc='Reading training data'):
            info = json.loads(info)
            trn_data.append(info['title'])

    with open(os.path.join(data_path, 'tst.json'), 'r') as fin:
        for info in tqdm(fin.readlines(), desc='Reading testing data'):
            info = json.loads(info)
            tst_data.append(info['title'])

    
    with open(os.path.join(data_path, 'lbl.json'), 'r') as fin:
        for info in tqdm(fin.readlines(), desc='Reading label data'):
            info = json.loads(info)
            lbl_data.append(info['title'])

    return trn_data, tst_data, lbl_data

def make_csr_tfidf(dataset):
    file_name = f'{dataset}/tfidf.npz'
    if os.path.exists(file_name):
        tfidf_mat = sp.load_npz(file_name)
    else:
        with open(f'{dataset}/train.txt') as fil:
            row_idx, col_idx, val_idx = [], [], []
            for i, data in enumerate(fil.readlines()):
                data = data.split()[1:]
                for tfidf in data:
                    try:
                        token, weight = tfidf.split(':')
                    except: 
                        print(f'Issue with token at line number {i}: {tfidf}')
                        continue
                    row_idx.append(i)
                    col_idx.append(int(token))
                    val_idx.append(float(weight))
            m = max(row_idx) + 1
            n = max(col_idx) + 1
            tfidf_mat = sp.csr_matrix((val_idx, (row_idx, col_idx)), shape=(m, n))
            sp.save_npz(file_name, tfidf_mat)
    return tfidf_mat

def make_csr_labels(num_labels, file_name):
    if os.path.exists(file_name):
        Y = sp.load_npz(file_name)
    else:
        with open(os.path.splitext(file_name)[0]+'.txt') as fil:
            row_idx, col_idx, val_idx = [], [], []
            for i, lab in enumerate(fil.readlines()):
                l_list = lab.replace('\n', '').split()
                for y in l_list:
                    row_idx.append(i)
                    col_idx.append(int(y))
                    val_idx.append(1)
            m = max(row_idx) + 1
            n = num_labels
            Y = sp.csr_matrix((val_idx, (row_idx, col_idx)), shape=(m, n))
            sp.save_npz(file_name, Y)
    return Y

def encode(text):
    return sp_token.encode(text, add_special_tokens=False)

# tokenizer = get_tokenizer(model)

def create_data(dataset, model):
    print(f"Creating new data for {model} model")
    tokenizer = get_tokenizer(model)
    global sp_token 
    sp_token = tokenizer

    # train_texts, test_texts, lbl_texts = load_short_data(dataset)
    train_texts, test_texts = [], []
    with open(f'{dataset}/train_raw_texts.txt') as f:
        for point in tqdm(f.readlines()):
            # train_texts.append(clean_str(point))
            point = point.replace('\n', ' ')
            point = point.replace('_', ' ')
            point = re.sub(r"\s{2,}", " ", point)
            point = re.sub("/SEP/", "[SEP]", point)
            train_texts.append(point)

    with open(f'{dataset}/test_raw_texts.txt') as f:
        for point in tqdm(f.readlines()):
            # test_texts.append(clean_str(point))
            # test_texts.append(point.replace('\n', ''))
            point = point.replace('\n', ' ')
            point = point.replace('_', ' ')
            point = re.sub(r"\s{2,}", " ", point)
            point = re.sub("/SEP/", "[SEP]", point)
            test_texts.append(point)
    
    print(f"Available CPU Count is: {cpu_count()}")

    os.makedirs(f'{dataset}/{model}', exist_ok=True)

    with Pool(cpu_count() - 1) as p:
        encoded_train = process_map(encode, train_texts, max_workers=cpu_count()-1, chunksize=100)

    with open(f'{dataset}/{model}/train_encoded.pkl', 'wb') as f:
        pkl.dump(encoded_train, f)

    with Pool(cpu_count() - 1) as p:
        encoded_test = process_map(encode, test_texts, max_workers=cpu_count()-1, chunksize=100)

    with open(f'{dataset}/{model}/test_encoded.pkl','wb') as f:
        pkl.dump(encoded_test, f)

def load_data(dataset, model, num_labels, load_precomputed): 
    train_labels, test_labels = [], []
    train_texts, test_texts = [], []
    
    print(f"Loading data for {dataset}")

    assert any([x in model for x in ['roberta', 'bert', 'xlnet']]), f'Tokenizer for {model} not implemented. Add it src/data_utils.py and rerun'

    if not os.path.exists(f'{dataset}/{model}/train_encoded.pkl'):
        create_data(dataset, model)
    
    with open(f'{dataset}/{model}/train_encoded.pkl', 'rb') as f:
        train_texts = pkl.load(f)
    
    # if dataset == './data/Wiki-500K':
    #     print("truncating train texts")
    #     for i, text in enumerate(train_texts):
    #          train_texts[i] = text[:128]

    with open(f'{dataset}/{model}/test_encoded.pkl', 'rb') as f:
        test_texts = pkl.load(f)

    # with open(f'{dataset}/{model}/lbl_encoded.pkl', 'rb') as f:
    #     lbl_texts = pkl.load(f)

    # if dataset == './data/Wiki-500K':
    #     print("truncating test texts")
    #    	for i, text in enumerate(test_texts):
    #    	     test_texts[i] = text[:128]
    
    train_labels = make_csr_labels(num_labels, f'{dataset}/Y.trn.npz')
    test_labels = make_csr_labels(num_labels, f'{dataset}/Y.tst.npz')
    tfidf = make_csr_tfidf(dataset)
    inv_prop = get_inv_prop(dataset, train_labels)

    return train_texts, test_texts, train_labels, test_labels, tfidf, inv_prop

def load_group(dataset, num_clusters):
    if dataset == 'wiki500k':
        return np.load(f'Wiki-500K/label_group_{num_clusters}.npy', allow_pickle=True)
    if dataset == 'Amazon-670K':
        return np.load(f'Amazon-670K/label_group_{num_clusters}.npy', allow_pickle=True) 
        # return np.load(f'Amazon-670K/label_group_tree-Level-1.npy', allow_pickle=True)
    if dataset == 'AT670':
        # return np.load(f'AmazonTitles-670K/label_group_{num_clusters}.npy', allow_pickle=True)
        return np.load(f'AmazonTitles-670K/label_group8192.npy', allow_pickle=True)
    if dataset == 'WSAT':
        return np.load(f'WikiSeeAlsoTitles-350K/label_group_{num_clusters}.npy', allow_pickle=True)  
    if dataset == 'LF-AmazonTitles-131K':
        return np.load(f'../Datasets/{dataset}/label_group_0.npy', allow_pickle=True)            

def load_cluster_tree(dataset, levels=2):
    if dataset == 'Amazon-670K':
        return [np.load(f'./data/Amazon-670K/label_group_tree-Level-{i}.npy', allow_pickle=True) for i in range(levels)]
        # return [np.load(f'Amazon-670K/label_group_stable-Level-{i}.npy', allow_pickle=True) for i in [1, 2]]
