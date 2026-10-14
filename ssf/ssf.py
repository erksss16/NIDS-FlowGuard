import torch
import numpy as np
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import TensorDataset
from sklearn.model_selection import train_test_split
from utils import *

import argparse
import warnings
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings('ignore')

def extract_flow_info(df, dataset):
    """Extract key flow features before normalization."""
    if dataset == 'nsl':
        proto_cols = ['protocol_type_icmp', 'protocol_type_tcp', 'protocol_type_udp']
        protocol = df[proto_cols].idxmax(axis=1).str.replace('protocol_type_', '')
        service_cols = [c for c in df.columns if c.startswith('service_')]
        service = df[service_cols].idxmax(axis=1).str.replace('service_', '')
        flag_cols = [c for c in df.columns if c.startswith('flag_')]
        flag = df[flag_cols].idxmax(axis=1).str.replace('flag_', '')
        return pd.DataFrame({
            'protocol': protocol, 'service': service, 'flag': flag,
            'src_bytes': df['src_bytes'], 'dst_bytes': df['dst_bytes'],
            'duration': df['duration'], 'true_label': df['labels5'],
        })
    else:
        proto_cols = [c for c in df.columns if c.startswith('proto_')]
        protocol = df[proto_cols].idxmax(axis=1).str.replace('proto_', '')
        service_cols = [c for c in df.columns if c.startswith('service_')]
        service = df[service_cols].idxmax(axis=1).str.replace('service_', '')
        return pd.DataFrame({
            'protocol': protocol, 'service': service, 'flag': '',
            'src_bytes': df['sbytes'], 'dst_bytes': df['dbytes'],
            'duration': df['dur'], 'true_label': df['label'],
        })


def make_tensor_batch(df, splitter, dataset, device=None):
    labels = 'labels2' if dataset == 'nsl' else 'label'
    flow_info = extract_flow_info(df, dataset).reset_index(drop=True)
    x_batch, y_batch = splitter.transform(df, labels=labels, fit_scaler=False)
    x_batch = torch.FloatTensor(x_batch)
    y_batch = torch.LongTensor(y_batch)
    if device is not None:
        x_batch = x_batch.to(device)
    return x_batch, y_batch, flow_info


def iter_tensor_batches(x_data, y_data, flow_info, min_batch, max_batch, device):
    start_idx = 0
    while start_idx < len(x_data):
        batch_size = random.randint(min_batch, max_batch)
        end_idx = min(start_idx + batch_size, len(x_data))
        yield (
            x_data[start_idx:end_idx].to(device),
            y_data[start_idx:end_idx],
            flow_info.iloc[start_idx:end_idx].copy(),
            start_idx,
            False,
        )
        start_idx = end_idx


def iter_stream_batches(
        heldout_x, heldout_y, heldout_flow, test_path, splitter, dataset,
        min_batch, max_batch, device, delay_seconds=0.0):
    global_start_idx = 0

    # First stream the 80% held-out training traffic, then the independent test set.
    for x_batch, y_batch, flow_batch, local_start, _ in iter_tensor_batches(
            heldout_x, heldout_y, heldout_flow, min_batch, max_batch, device):
        yield x_batch, y_batch, flow_batch, global_start_idx + local_start, False
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    global_start_idx += len(heldout_x)
    for chunk in pd.read_csv(test_path, chunksize=random.randint(min_batch, max_batch)):
        x_batch, y_batch, flow_batch = make_tensor_batch(chunk, splitter, dataset, device=device)
        yield x_batch, y_batch, flow_batch, global_start_idx, True
        global_start_idx += len(x_batch)
        if delay_seconds > 0:
            time.sleep(delay_seconds)


parser = argparse.ArgumentParser(description='manual to this script')
parser.add_argument("--dataset", type=str, default='unsw')
parser.add_argument("--epochs", type=int, default=4)
parser.add_argument("--epoch_1", type=int, default=1)
parser.add_argument("--percent", type=float, default=0.2, help="Held-out ratio from train CSV used as the online stream when not using --stream")
parser.add_argument("--pretrain-ratio", type=float, default=None, help="Explicit initial training ratio; overrides --percent with percent=1-pretrain_ratio")
parser.add_argument("--min-sample-interval", type=int, default=20000)
parser.add_argument("--max-sample-interval", type=int, default=20000)
parser.add_argument("--sample_interval", type=int, default=None, help="Backward-compatible alias for setting min and max sample interval")
parser.add_argument("--cuda", type=str, default="2")
parser.add_argument("--num_labeled_sample", type=int, default=200)
parser.add_argument("--opt_new_lr", type=float, default=50.0)
parser.add_argument("--opt_old_lr", type=float, default=1.0)
parser.add_argument("--new_sample_weight", type=float, default=100.0, help="Weight for new samples in the loss calculation")
parser.add_argument("--drift-threshold", type=float, default=0.05, help="Reserved drift threshold argument; fdd-multidim estimates its active threshold from reference data")
parser.add_argument("--drift-method", choices=["fdd", "fdd-multidim"], default="fdd-multidim", help="Drift detection method")
parser.add_argument("--save_ckpt", type=str, default="", help="Path to save checkpoint after initial training, e.g. ckpt_nsl.pth")
parser.add_argument("--load_ckpt", type=str, default="", help="Path to load checkpoint to skip initial training")
parser.add_argument("--mysql", action="store_true", default=False, help="Log online detection results to the configured database")
parser.add_argument("--db-backend", choices=["sqlite", "mysql"], default=os.getenv("NIDS_DB_BACKEND", "sqlite"), help="Database backend used when --mysql is enabled")
parser.add_argument("--sqlite-path", type=str, default=os.getenv("NIDS_SQLITE_PATH", "../data/ssf.sqlite3"), help="SQLite database path")
parser.add_argument("--skip_initial_eval", action="store_true", default=False, help="Skip the expensive pre-online evaluation so live results are written sooner")
parser.add_argument("--stream", action="store_true", default=False, help="Read online test traffic from CSV chunks to simulate real-time arrivals")
parser.add_argument("--stream-delay", type=float, default=0.0, help="Seconds to wait after each streamed CSV chunk")
parser.add_argument("--seed", type=int, default=5011)
parser.add_argument("--seed-rounds", type=int, default=5)


args = parser.parse_args()
dataset = args.dataset
epochs = args.epochs
epoch_1 = args.epoch_1
percent = args.percent
if args.pretrain_ratio is not None:
    percent = 1.0 - args.pretrain_ratio
min_sample_interval = args.min_sample_interval
max_sample_interval = args.max_sample_interval
if args.sample_interval is not None:
    min_sample_interval = args.sample_interval
    max_sample_interval = args.sample_interval
cuda_num = args.cuda
num_labeled_sample = args.num_labeled_sample
opt_new_lr = args.opt_new_lr
opt_old_lr = args.opt_old_lr
new_sample_weight = args.new_sample_weight
drift_threshold = args.drift_threshold
drift_method = args.drift_method
save_ckpt = args.save_ckpt
load_ckpt = args.load_ckpt
use_mysql = args.mysql
db_backend = args.db_backend
sqlite_path = args.sqlite_path
skip_initial_eval = args.skip_initial_eval
stream_mode = args.stream
stream_delay = args.stream_delay

seed = args.seed
seed_round = args.seed_rounds
old_init = '0.5-1'
new_init = '0-0.5'
lwf_lambda = 0.5

tem = 0.02
bs = 128

if dataset == 'nsl':
    input_dim = 121
else:
    input_dim = 196


if dataset == 'nsl':
    KDDTrain_dataset_path   = "NSL_pre_data/PKDDTrain+.csv"
    KDDTest_dataset_path    = "NSL_pre_data/PKDDTest+.csv"

    KDDTrain   =  load_data(KDDTrain_dataset_path)
    KDDTest    =  None if stream_mode else load_data(KDDTest_dataset_path)

    splitter_nsl = SplitData(dataset='nsl')
else:
    UNSWTrain_dataset_path   = "UNSW_pre_data/UNSWTrain.csv"
    UNSWTest_dataset_path    = "UNSW_pre_data/UNSWTest.csv"

    UNSWTrain   =  load_data(UNSWTrain_dataset_path)
    UNSWTest    =  None if stream_mode else load_data(UNSWTest_dataset_path)

    splitter_unsw = SplitData(dataset='unsw')

if not torch.cuda.is_available():
    raise RuntimeError(
        "CUDA GPU is required for SSF, but this Python environment has CPU-only PyTorch "
        "or cannot access CUDA. Install a CUDA-enabled PyTorch build and rerun start.ps1."
    )
device = torch.device("cuda:" + cuda_num)
print(f"Using CUDA device {device}: {torch.cuda.get_device_name(int(cuda_num))}")

if use_mysql:
    if db_backend == "mysql":
        import pymysql
        mysql_conn = pymysql.connect(
            host=os.getenv("NIDS_MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("NIDS_MYSQL_PORT", "3306")),
            user=os.getenv("NIDS_MYSQL_USER", "admin"),
            password=os.getenv("NIDS_MYSQL_PASSWORD", "hust2026"),
            database=os.getenv("NIDS_MYSQL_DATABASE", "ssf"),
            charset='utf8mb4'
        )
        mysql_cur = mysql_conn.cursor()
        mysql_cur.execute("""
            CREATE TABLE IF NOT EXISTS detection_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                run_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                seed INT NOT NULL,
                iteration INT NOT NULL,
                drift_detected TINYINT(1) NOT NULL,
                protocol VARCHAR(20),
                service VARCHAR(30),
                flag VARCHAR(10),
                src_bytes DOUBLE,
                dst_bytes DOUBLE,
                duration DOUBLE,
                true_label VARCHAR(30),
                predicted_label VARCHAR(30),
                drift_score DOUBLE,
                drift_level VARCHAR(10),
                INDEX idx_seed_iter (seed, iteration)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        mysql_cur.execute("""
            CREATE TABLE IF NOT EXISTS final_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                run_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                seed INT NOT NULL,
                accuracy DOUBLE,
                precision_score DOUBLE,
                recall DOUBLE,
                f1_score DOUBLE,
                UNIQUE KEY uk_seed (seed)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        mysql_cur.execute("SHOW COLUMNS FROM detection_results")
        detection_columns = {row[0] for row in mysql_cur.fetchall()}
        if "drift_score" not in detection_columns:
            mysql_cur.execute("ALTER TABLE detection_results ADD COLUMN drift_score DOUBLE")
        if "drift_level" not in detection_columns:
            mysql_cur.execute("ALTER TABLE detection_results ADD COLUMN drift_level VARCHAR(10)")
        db_placeholder = "%s"
        db_final_sql = (
            "INSERT INTO final_results (seed, accuracy, precision_score, recall, f1_score) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE accuracy=VALUES(accuracy), precision_score=VALUES(precision_score), "
            "recall=VALUES(recall), f1_score=VALUES(f1_score)"
        )
    else:
        sqlite_db_path = Path(sqlite_path)
        sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        mysql_conn = sqlite3.connect(sqlite_db_path)
        mysql_cur = mysql_conn.cursor()
        mysql_cur.execute("""
            CREATE TABLE IF NOT EXISTS detection_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT DEFAULT CURRENT_TIMESTAMP,
                seed INTEGER NOT NULL,
                iteration INTEGER NOT NULL,
                drift_detected INTEGER NOT NULL,
                protocol TEXT,
                service TEXT,
                flag TEXT,
                src_bytes REAL,
                dst_bytes REAL,
                duration REAL,
                true_label TEXT,
                predicted_label TEXT,
                drift_score REAL,
                drift_level TEXT
            )
        """)
        mysql_cur.execute("CREATE INDEX IF NOT EXISTS idx_detection_seed_iter ON detection_results (seed, iteration)")
        mysql_cur.execute("PRAGMA table_info(detection_results)")
        detection_columns = {row[1] for row in mysql_cur.fetchall()}
        if "drift_score" not in detection_columns:
            mysql_cur.execute("ALTER TABLE detection_results ADD COLUMN drift_score REAL")
        if "drift_level" not in detection_columns:
            mysql_cur.execute("ALTER TABLE detection_results ADD COLUMN drift_level TEXT")
        mysql_cur.execute("""
            CREATE TABLE IF NOT EXISTS final_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT DEFAULT CURRENT_TIMESTAMP,
                seed INTEGER NOT NULL UNIQUE,
                accuracy REAL,
                precision_score REAL,
                recall REAL,
                f1_score REAL
            )
        """)
        db_placeholder = "?"
        db_final_sql = (
            "INSERT INTO final_results (seed, accuracy, precision_score, recall, f1_score) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(seed) DO UPDATE SET accuracy=excluded.accuracy, "
            "precision_score=excluded.precision_score, recall=excluded.recall, f1_score=excluded.f1_score"
        )
    mysql_conn.commit()
    print(f'{db_backend.upper()} connected, tables ready.')

criterion = InfoNCELoss(device, tem)
if dataset != 'nsl':
    classification_criterion = nn.BCELoss(reduction='none')

for i in range(seed_round):
    # Set the seed for the random number generator for this iteration
    # setup_seed(seed+i)
    current_seed = seed+i
    setup_seed(current_seed)
    print(f"Current seed: {current_seed}")

    if dataset == 'nsl':
        flow_info_train = extract_flow_info(KDDTrain, 'nsl')
        x_train, y_train = splitter_nsl.transform(KDDTrain, labels='labels2')
        if stream_mode:
            flow_info_test = None
            x_test, y_test = None, None
        else:
            flow_info_test = extract_flow_info(KDDTest, 'nsl')
            x_test, y_test = splitter_nsl.transform(KDDTest, labels='labels2', fit_scaler=False)
        splitter = splitter_nsl
        test_dataset_path = KDDTest_dataset_path
    else:
        flow_info_train = extract_flow_info(UNSWTrain, 'unsw')
        x_train, y_train = splitter_unsw.transform(UNSWTrain, labels='label')
        if stream_mode:
            flow_info_test = None
            x_test, y_test = None, None
        else:
            flow_info_test = extract_flow_info(UNSWTest, 'unsw')
            x_test, y_test = splitter_unsw.transform(UNSWTest, labels='label', fit_scaler=False)
        splitter = splitter_unsw
        test_dataset_path = UNSWTest_dataset_path

    # Convert to torch tensors
    x_train, y_train = torch.FloatTensor(x_train), torch.LongTensor(y_train)
    if not stream_mode:
        x_test, y_test = torch.FloatTensor(x_test), torch.LongTensor(y_test)
    print('shape of x_train ', x_train.shape)
    if stream_mode:
        print(f'streaming online test data from {test_dataset_path}, chunk size {min_sample_interval}-{max_sample_interval}, delay {stream_delay}s')
    else:
        print('shape of x_test is ', x_test.shape)

    torch.cuda.empty_cache()

    all_idx = np.arange(len(x_train))
    train_idx, test_idx = train_test_split(all_idx, test_size=percent)
    online_x_train, online_y_train = x_train[train_idx], y_train[train_idx]
    online_x_test, online_y_test = x_train[test_idx], y_train[test_idx]
    flow_online_train = flow_info_train.iloc[train_idx].reset_index(drop=True)
    flow_online_test = flow_info_train.iloc[test_idx].reset_index(drop=True)
    memory = x_train.shape[0] * (1-percent)
    print('size of memory is ', memory)
    memory = math.floor(memory)

    train_ds = TensorDataset(online_x_train, online_y_train)
    train_loader = torch.utils.data.DataLoader(
        dataset=train_ds, batch_size=bs, shuffle=True)
    
    num_of_first_train = online_x_train.shape[0]

    if dataset == 'nsl':
        model = AE(input_dim).to(device)
        teacher_model = AE(input_dim).to(device)
    else:
        model = AE_classifier(input_dim).to(device)
        teacher_model = AE_classifier(input_dim).to(device)

    optimizer = torch.optim.SGD(model.parameters(), lr= 0.001)

    if load_ckpt:
        print(f'Loading checkpoint from {load_ckpt}')
        ckpt = torch.load(load_ckpt, map_location=device)
        model.load_state_dict(ckpt['model_state_dict'])
        optimizer.load_state_dict(ckpt['optimizer_state_dict'])
        print('Checkpoint loaded, skipping initial training.')
    else:
        model.train()
        for epoch in range(epochs):
            if epoch % 50 == 0 or epoch == 0:
                print('seed = ', (seed+i), ', first round: epoch = ', epoch)
            for j, data in enumerate(train_loader, 0):
                inputs, labels = data
                inputs = inputs.to(device)

                labels = labels.to(device)
                optimizer.zero_grad()

                if dataset == 'nsl':
                    features, recon_vec = model(inputs)
                else:
                    features, recon_vec, classifications = model(inputs)
                con_loss = criterion(recon_vec,labels)
                if dataset == 'nsl':
                    loss = con_loss.mean()
                else:
                    classification_loss = classification_criterion(classifications.squeeze(), labels.float())
                    loss = con_loss.mean() + classification_loss.mean()

                loss.backward()
                optimizer.step()

        if save_ckpt:
            print(f'Saving checkpoint to {save_ckpt}')
            torch.save({
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'dataset': dataset,
                'epochs': epochs,
                'percent': percent,
                'seed': current_seed,
                'input_dim': input_dim,
            }, save_ckpt)
            print('Checkpoint saved, exiting.')
            break

    teacher_model.load_state_dict(model.state_dict())  # Initialize teacher model

    x_train = x_train.to(device)
    if not stream_mode:
        x_test = x_test.to(device)
    online_x_train, online_y_train  = online_x_train.to(device), online_y_train.to(device)

    x_train_this_epoch = online_x_train.clone()
    y_train_this_epoch = online_y_train.clone()

    if stream_mode:
        online_batches = iter_stream_batches(
            online_x_test, online_y_test, flow_online_test, test_dataset_path,
            splitter, dataset, min_sample_interval, max_sample_interval, device, stream_delay
        )
        stream_true_labels = []
        stream_pred_labels = []
        stream_labeled_indices = []
    else:
        x_test_left_epoch, y_test_left_epoch = online_x_test.clone().to(device), online_y_test.clone()
        permutation = torch.randperm(x_test.size(0))

        # Apply this permutation to both tensors to shuffle them in unison.
        x_test = x_test[permutation]
        y_test = y_test[permutation]
        # Concatenating x_test and x_test_left_epoch
        x_test_left_epoch = torch.cat((x_test_left_epoch, x_test), dim=0)
        print('shape of x_test_left_epoch is ', x_test_left_epoch.shape)
        # Concatenating y_test and y_test_left_epoch
        y_test_left_epoch = torch.cat((y_test_left_epoch, y_test), dim=0)

        flow_test_left_epoch = pd.concat([flow_online_test, flow_info_test.iloc[permutation.cpu().numpy()].reset_index(drop=True)], ignore_index=True)
        online_batches = iter_tensor_batches(
            x_test_left_epoch, y_test_left_epoch, flow_test_left_epoch, min_sample_interval, max_sample_interval, device
        )

    if dataset == 'nsl':
        normal_recon_temp = torch.mean(F.normalize(model(online_x_train[(online_y_train == 0).squeeze()])[1], p=2, dim=1), dim=0)
        if skip_initial_eval or stream_mode:
            print('Skipping performance_before_continual_training to start live detection sooner.')
        else:
            y_pred_before_online = evaluate(normal_recon_temp, online_x_train, online_y_train, x_test_left_epoch, 0, model, device=device)
            y_pred_before_online = y_pred_before_online.cpu().numpy()
            print('--------------------------- performance_before_continual_training -----------------------------------')
            performance_before = score_detail(y_test_left_epoch[-x_test.shape[0]:].numpy(), y_pred_before_online[-x_test.shape[0]:].astype("int32"))
    else:
        if stream_mode:
            print('Skipping performance_before_contunual_training to start live detection sooner.')
        else:
            print('--------------------------- performance_before_contunual_training -----------------------------------')
            test_ds = TensorDataset(x_test, y_test)  # Replace with your test data
            test_loader = DataLoader(dataset=test_ds, batch_size=bs, shuffle=False)
            performance_before = evaluate_classifier(model, test_loader, device)

####################### start online training #######################
    model = model.to(device)

    count = 0

    y_train_detection = torch.empty(0, dtype=torch.long, device=device)
    labeled_indices = []

    for x_test_this_epoch, y_test_this_epoch, flow_this_batch, batch_start_idx, is_streamed_test in online_batches:
        print('seed = ', (seed+i), ', i = ', count)
        count += 1
        
        model = model.to(device)

        if dataset == 'nsl':
            # must compute the normal_temp and normal_recon_temp again, because the model has been updated
            normal_recon_temp = torch.mean(F.normalize(model(x_train_this_epoch[(y_train_this_epoch == 0).squeeze()])[1], p=2, dim=1), dim=0)
            pdf1, pdf2, values1 = evaluate(normal_recon_temp, x_train_this_epoch, y_train_this_epoch, x_train_this_epoch, y_train_this_epoch, model, device=device, get_probs=True)
            pdf11, pdf22, values11 = evaluate(normal_recon_temp, x_train_this_epoch, y_train_this_epoch, x_test_this_epoch, 0, model, device=device, get_probs=True)
            
            pdf1_probe = pdf1 / (pdf1 + pdf2)
            pdf11_probe = pdf11 / (pdf11 + pdf22)

            drift, drift_score, drift_level = detect_drift(
                pdf11_probe,
                pdf1_probe,
                len(x_test_this_epoch),
                drift_threshold,
                method=drift_method,
            )

            control_res = pdf1_probe.cpu().numpy()
            treatment_res = pdf11_probe.cpu().numpy()
        else:
            # Get logits for drift detection
            with torch.no_grad():
                _, _, test_logits = model(x_test_this_epoch)
                test_logits = test_logits.squeeze()

            with torch.no_grad():
                _, _, train_logits = model(x_train_this_epoch)
                train_logits = train_logits.squeeze()

            drift, drift_score, drift_level = detect_drift(
                test_logits,
                train_logits,
                len(x_test_this_epoch),
                drift_threshold,
                method=drift_method,
            )
            control_res = train_logits.cpu().numpy()
            treatment_res = test_logits.cpu().numpy()

        if drift_level == "high":
            batch_new_sample_weight = new_sample_weight * 1.5
            batch_lwf_lambda = lwf_lambda * 0.5
        elif drift_level == "medium":
            batch_new_sample_weight = new_sample_weight * 1.2
            batch_lwf_lambda = lwf_lambda * 0.8
        elif drift_level == "low":
            batch_new_sample_weight = new_sample_weight
            batch_lwf_lambda = lwf_lambda
        else:
            batch_new_sample_weight = max(1.0, new_sample_weight * 0.75)
            batch_lwf_lambda = lwf_lambda * 1.2
        print(f"Drift score={drift_score:.6f}, level={drift_level}, new_sample_weight={batch_new_sample_weight:.3f}, lwf_lambda={batch_lwf_lambda:.3f}")

        # Optimize masks for old and new data
        M_c = optimize_old_mask(control_res, treatment_res, device, initialization=old_init, lr=opt_old_lr)
        M_t = optimize_new_mask(control_res, treatment_res, M_c, device, initialization=new_init, lr=opt_new_lr)

        y_test_this_epoch = y_test_this_epoch.to(device)

        # Detect Drift
        if drift:
            print("Drift detected, update the model...")
            # Select and update representative samples
            if dataset == 'nsl':
                x_train_this_epoch, y_train_this_epoch, labeled_indices_current, new_mask = select_and_update_representative_samples_when_drift(
                    x_train_this_epoch, y_train_this_epoch, x_test_this_epoch, y_test_this_epoch, M_c, M_t, num_labeled_sample, device, memory, model, normal_recon_temp
                )
            else:
                x_train_this_epoch, y_train_this_epoch, labeled_indices_current, new_mask = select_and_update_representative_samples_when_drift(
                    x_train_this_epoch, y_train_this_epoch, x_test_this_epoch, y_test_this_epoch, M_c, M_t, num_labeled_sample, device, memory, model
                )
        else:
            # Select and update representative samples
            x_train_this_epoch, y_train_this_epoch, labeled_indices_current, new_mask = select_and_update_representative_samples(
                x_train_this_epoch, y_train_this_epoch, x_test_this_epoch, y_test_this_epoch, M_c, M_t, num_labeled_sample, device
            )

        labeled_indices.append(batch_start_idx + labeled_indices_current.cpu().numpy())

        # Re-training model
        train_ds = TensorDataset(x_train_this_epoch, y_train_this_epoch, new_mask)
        train_loader = torch.utils.data.DataLoader(dataset=train_ds, batch_size=bs, shuffle=True)
        
        model = model.to(device)
        model.train()

        if drift:            
            for epoch in range(epoch_1):
                if epoch % 50 == 0:
                    print('epoch = ', epoch)
                for j, data in enumerate(train_loader, 0):
                    inputs, labels, new_sample_mask = data
                    inputs = inputs.to(device)
                    labels = labels.to(device)
                    new_sample_mask = new_sample_mask.to(device)
                    normal_new_mask = new_sample_mask[labels == 0]
                    
                    optimizer.zero_grad()
                    
                    if dataset == 'nsl':
                        features, recon_vec = model(inputs)
                    else:
                        features, recon_vec, classifications = model(inputs)

                    con_loss = criterion(recon_vec, labels)
                    weighted_con_loss = con_loss * ((1 - normal_new_mask) + normal_new_mask * batch_new_sample_weight)

                    if dataset == 'nsl':
                        weighted_loss = weighted_con_loss.mean()
                    else:
                        classification_loss = classification_criterion(classifications.squeeze(), labels.float())
                        weighted_classification_loss = classification_loss * ((1 - new_sample_mask) + new_sample_mask * batch_new_sample_weight)
                        weighted_loss = weighted_con_loss.mean() + weighted_classification_loss.mean()

                    weighted_loss.backward()
                    optimizer.step()
        else:      
            for epoch in range(epoch_1):
                if epoch % 50 == 0:
                    print('epoch = ', epoch)
                for j, data in enumerate(train_loader, 0):
                    inputs, labels, new_sample_mask = data
                    inputs = inputs.to(device)
                    labels = labels.to(device)
                    new_sample_mask = new_sample_mask.to(device)
                    normal_new_mask = new_sample_mask[labels == 0]
                    
                    optimizer.zero_grad()
                    
                    if dataset == 'nsl':
                        features, recon_vec = model(inputs)
                    else:
                        features, recon_vec, classifications = model(inputs)

                    con_loss = criterion(recon_vec, labels)
                    weighted_con_loss = con_loss * ((1 - normal_new_mask) + normal_new_mask * batch_new_sample_weight)

                    if dataset == 'nsl':
                        weighted_loss = weighted_con_loss.mean()
                    else:
                        classification_loss = classification_criterion(classifications.squeeze(), labels.float())
                        weighted_classification_loss = classification_loss * ((1 - new_sample_mask) + new_sample_mask * batch_new_sample_weight)
                        weighted_loss = weighted_con_loss.mean() + weighted_classification_loss.mean()

                    # Apply the new sample weight using the mask
                    # weighted_loss = (1 - mask) * loss + mask * new_sample_weight * loss

                    if dataset == 'nsl':
                        with torch.no_grad():
                            teacher_features, teacher_recon_vec = teacher_model(inputs)
                        distillation_loss = F.mse_loss(recon_vec, teacher_recon_vec)
                    else:
                        with torch.no_grad():
                            teacher_features, teacher_recon_vec, teacher_logits = teacher_model(inputs)
                        distillation_loss = F.mse_loss(classifications, teacher_logits)
                    total_loss = weighted_loss + batch_lwf_lambda * distillation_loss

                    total_loss.backward()
                    optimizer.step()
        
        teacher_model.load_state_dict(model.state_dict())  # Update teacher model

        if dataset == 'nsl':
            # normal_temp = torch.mean(F.normalize(model(x_train_this_epoch[(y_train_this_epoch == 0).squeeze()])[0], p=2, dim=1), dim=0)
            normal_recon_temp = torch.mean(F.normalize(model(x_train_this_epoch[(y_train_this_epoch == 0).squeeze()])[1], p=2, dim=1), dim=0)
            predict_label = evaluate(normal_recon_temp, x_train_this_epoch, y_train_this_epoch, x_test_this_epoch, 0, model, device=device)
        else:
            test_ds = TensorDataset(x_test_this_epoch, y_test_this_epoch)  # Replace with your test data
            test_loader = DataLoader(dataset=test_ds, batch_size=bs, shuffle=False)
            predict_label = evaluate_classifier(model, test_loader, device, get_predict=True)
        
        pred_tensor = torch.as_tensor(predict_label, dtype=torch.long, device=device)
        y_train_detection = torch.cat((y_train_detection.to(device), pred_tensor))

        if stream_mode and is_streamed_test:
            stream_true_labels.append(y_test_this_epoch.detach().cpu())
            stream_pred_labels.append(pred_tensor.detach().cpu())
            stream_labeled_indices.append(labeled_indices_current.detach().cpu().numpy())

        if use_mysql:
            if isinstance(predict_label, np.ndarray):
                pred_np = predict_label
            elif torch.is_tensor(predict_label):
                pred_np = predict_label.detach().cpu().numpy()
            else:
                pred_np = np.asarray(predict_label)
            batch_rows = []
            batch_time = datetime.now()
            for row_idx in range(len(pred_np)):
                flow = flow_this_batch.iloc[row_idx]
                batch_rows.append((
                    (batch_time + timedelta(seconds=row_idx // 4)).strftime('%Y-%m-%d %H:%M:%S'),
                    current_seed, count, int(drift),
                    flow['protocol'], flow['service'], flow.get('flag', ''),
                    float(flow['src_bytes']), float(flow['dst_bytes']), float(flow['duration']),
                    str(flow['true_label']), 'attack' if pred_np[row_idx] == 1 else 'normal',
                    float(drift_score), drift_level
            ))
            mysql_cur.executemany(
                f"INSERT INTO detection_results (run_time, seed, iteration, drift_detected, protocol, service, flag, src_bytes, dst_bytes, duration, true_label, predicted_label, drift_score, drift_level) VALUES ({', '.join([db_placeholder] * 14)})",
                batch_rows
            )
            mysql_conn.commit()

################### test the performance after online training ###################

    print('--------------------------- performance_after_continual_training -----------------------------------')

    if stream_mode:
        if stream_true_labels:
            y_test_left_true = torch.cat(stream_true_labels)
            y_test_left_pseudo = torch.cat(stream_pred_labels)
            test_mask = np.ones(len(y_test_left_true), dtype=bool)
            offset = 0
            for labels, batch_labeled_indices in zip(stream_true_labels, stream_labeled_indices):
                test_mask[offset + batch_labeled_indices] = False
                offset += len(labels)
            if not test_mask.any():
                print('All streamed samples were selected as representative labels; scoring all streamed predictions.')
                test_mask = np.ones(len(y_test_left_true), dtype=bool)
            performance_test = score_detail(
                y_test_left_true[test_mask].numpy(),
                y_test_left_pseudo[test_mask].numpy()
            )
        else:
            print('No streamed test samples were processed; skipping final performance score.')
            performance_test = (0, 0, 0, 0)
    else:
        test_size = len(x_test)
        total_size = len(x_test_left_epoch)

        # Convert list of numpy arrays to a single numpy array
        all_labeled_indices = np.hstack(labeled_indices)

        # Mask to denote indexes with true label
        mask = np.ones(total_size, dtype=bool)
        mask[all_labeled_indices] = False

        # get the mask to denote indexes that have been true-labeled in the test dataset
        test_mask = mask[-test_size:]

        # obtain true and pseudo labels in test dataset
        y_test_left_pseudo = y_train_detection[-test_size:][test_mask].to(device)
        y_test_left_true = y_test_left_epoch[-test_size:][test_mask].to(device)

        performance_test = score_detail(y_test_left_true.cpu().numpy(), y_test_left_pseudo.cpu().numpy())

    if use_mysql:
        mysql_cur.execute(
            db_final_sql,
            (current_seed, float(performance_test[0]), float(performance_test[1]), float(performance_test[2]), float(performance_test[3]))
        )
        mysql_conn.commit()
