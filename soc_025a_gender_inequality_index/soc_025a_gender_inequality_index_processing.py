import pandas as pd
import io
import requests
import os
from carto.datasets import DatasetManager
from carto.auth import APIKeyAuthClient
import boto3
from zipfile import ZipFile
from botocore.exceptions import NoCredentialsError

# name of table on Carto where you want to upload data
# this should be a table name that is not currently in use
dataset_name = 'soc_025a_gender_inequality_index' #check

# set the directory that you are working in with the path variable
# you can use an environmental variable, as we did, or directly enter the directory name as a string
# example: path = '/home/cli_029a_vulnerability_to_cc'
dir = os.path.join(os.getenv('PROCESSING_DIR'), dataset_name)
#move to this directory
os.chdir(dir)

# create a new sub-directory within your specified dir called 'data'
data_dir = 'data'
if not os.path.exists(data_dir):
    os.mkdir(data_dir)

'''
Download data and save to your data directory
'''
# insert the url used to download the data from the source website
url = 'http://hdr.undp.org/sites/default/files/hdro_statistical_data_table_5.xlsx' #check

# read in data to pandas dataframe
r = requests.get(url)
df = pd.read_excel(io.BytesIO(r.content), encoding='utf8')

# save unprocessed source data to put on S3 (below)
raw_data_file = os.path.join(data_dir, os.path.basename(url))
df.to_excel(raw_data_file, header = False, index = False)

'''
Process data
'''

# drop header rows
df = df.iloc[7:] #check

# drop columns without data
df = df.drop(df.columns.difference(['Unnamed: 0','Table 5. Gender Inequality Index', 'Unnamed: 2','Unnamed: 4',
                                    'Unnamed: 6', 'Unnamed: 8','Unnamed: 10','Unnamed: 12', 'Unnamed: 14',
                                    'Unnamed: 16', 'Unnamed: 18']), 1) #check

#delete rows with missing values
df = df.dropna()

#rename columns
df.columns = ['HDI rank','Country','2018_GIIvalue', '2018_GIIrank', '2015 Maternal Mortality (per 1000 births)',
              '2015-2020 Adolescent birth rate (births per 1,000 women ages 15–19)',
              '2018 Share of seats in parliament','2010-2018 fem with secondary ed',
              '2010-2018 male with secondary ed', '2018 fem labor', '2018 male labor'] #check

#replace all '..' with None
df = df.replace({'..':None})
#replace all NaN with None
final_df=df.where((pd.notnull(df)), None)

#save processed dataset to csv
processed_data_file = os.path.join(data_dir, dataset_name+'_edit.csv')
final_df.to_csv(processed_data_file, index=False)

'''
Upload processed data to Carto
'''
print('Uploading processed data to Carto.')
#set up carto authentication using local variables for username (CARTO_WRI_RW_USER) and API key (CARTO_WRI_RW_KEY)
auth_client = APIKeyAuthClient(api_key=os.getenv('CARTO_WRI_RW_KEY'), base_url="https://{user}.carto.com/".format(user=os.getenv('CARTO_WRI_RW_USER')))
print (os.getenv('CARTO_WRI_RW_KEY'))
#set up dataset manager with authentication
dataset_manager = DatasetManager(auth_client)
#upload dataset to carto
dataset = dataset_manager.create(processed_data_file)
print('Carto table created: {}'.format(os.path.basename(processed_data_file).split('.')[0]))
#set dataset privacy to 'Public with link'
dataset.privacy = 'LINK'
dataset.save()
print('Privacy set to public with link.')

'''
Upload original data and processed data to Amazon S3 storage
'''
def upload_to_aws(local_file, bucket, s3_file):
    s3 = boto3.client('s3', aws_access_key_id=os.getenv('aws_access_key_id'),
                      aws_secret_access_key=os.getenv('aws_secret_access_key'))
    try:
        s3.upload_file(local_file, bucket, s3_file)
        print("Upload Successful")
        print("http://{}.s3.amazonaws.com/{}".format(bucket, s3_file))
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False

print('Uploading original data to S3.')
# Copy the raw data into a zipped file to upload to S3
raw_data_dir = os.path.join(data_dir, dataset_name+'.zip')
with ZipFile(raw_data_dir, 'w') as zip:
    zip.write(raw_data_file, os.path.basename(raw_data_file))

# Upload raw data file to S3
uploaded = upload_to_aws(raw_data_dir, 'wri-public-data', 'resourcewatch/'+os.path.basename(raw_data_dir))

print('Uploading processed data to S3.')
# Copy the processed data into a zipped file to upload to S3
processed_data_dir = os.path.join(data_dir, dataset_name+'_edit.zip')
with ZipFile(processed_data_dir, 'w') as zip:
    zip.write(processed_data_file, os.path.basename(processed_data_file))

# Upload processed data file to S3
uploaded = upload_to_aws(processed_data_dir, 'wri-public-data', 'resourcewatch/'+os.path.basename(processed_data_dir))