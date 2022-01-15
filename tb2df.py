import tensorflow as tf
import re
from pathlib import Path
import pandas as pd

def get_data_from_path(event_path):
    dir_name = Path(event_path).parent
    data = list()
    match = re.search(r'^(\w*)-(\d)-(.+)$', dir_name.name[:-9])
    cfg = match.group(1)
    run = match.group(2)
    msg = match.group(3)
    cfg = f'{cfg}-{msg}'
    assert cfg and run and msg

    for e in tf.train.summary_iterator(event_path):
        try:
            summary = e.summary
            step = e.step
            value = summary.value
        except AttributeError:
            continue

        if len(value) == 0:
            continue

        assert len(value) == 1, value
        value = value[0]
        tag = value.tag 
        if tag == 'custom_scalars__config__':
            continue

        value = value.simple_value
        data.append((step, tag, value))
    df = pd.DataFrame(data, columns=['step', 'tag', 'value'])
    df['cfg'] = cfg
    df['run'] = f'run-{run}' # Do not use numerical data. seaborn isn't happy with that.
    return df

def get_data(logdir):
    dfs = list()
    for path in Path(logdir).iterdir():
        events = list(path.glob('events*'))
        assert len(events) == 1, path
        event_path = str(events[0])
        loop_df = get_data_from_path(event_path)
        dfs.append(loop_df)
    df = pd.concat(dfs)
    print(len(df))
    return df
