import pandas as pd
import numpy as np

SERVICES = [
    'onlinesecurity', 'onlinebackup', 'deviceprotection',
    'techsupport', 'streamingtv', 'streamingmovies'
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['total_services'] = df[SERVICES].apply(lambda x: (x == 'Yes').sum(), axis=1)
    # astype('string') before .str: a column that is entirely blank reads as
    # float64 from read_csv, and the .str accessor raises
    # "Can only use .str accessor with string values, not floating" -- an
    # error naming pandas internals rather than the actual problem. na=False
    # already handles *individual* missing values; this handles the
    # whole-column dtype change, so both degrade to is_auto_pay=0 the same
    # way. The batch path rejects such a column earlier with a readable
    # message (config.validate_input_frame), but engineer_features() is
    # imported by the notebook and the API too, so it guards itself.
    df['is_auto_pay'] = (
        df['paymentmethod'].astype('string')
        .str.contains('automatic', case=False, na=False)
        .astype(int)
    )
    df['family_tie'] = ((df['partner'] == 'Yes') | (df['dependents'] == 'Yes')).astype(int)
    df['contractvstenure'] = df['contract'].map({'Month-to-month': 1, 'One year': 2, 'Two year': 3}) * df['tenure']
    df['average_monthly_charges'] = np.where(
        df['tenure'] > 0, #avoid division by zero and NaN values for new customers with tenure=0
        df['totalcharges'] / df['tenure'],
        df['monthlycharges']
    )
    df['charge_change_ratio'] = np.where(
        df['average_monthly_charges'] > 0, #avoid division by zero and NaN values for new customers with average_monthly_charges=0
        df['monthlycharges'] / df['average_monthly_charges'],
        1.0
    )
    return df