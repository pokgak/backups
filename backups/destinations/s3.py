import os, os.path
import subprocess
import logging

import boto.s3

import dateutil.parser

from backups.exceptions import BackupException
from backups.destinations import backupdestination
from backups.destinations.destination import BackupDestination

@backupdestination('s3')
class S3(BackupDestination):
    def __init__(self, config):
        BackupDestination.__init__(self, config)
        self.bucket = config.get('s3', 'bucket')
        try:
            self.az = config.get('s3', 'availability_zone')
        except:
            self.az = config.get_or_envvar('defaults', 'availability_zone', 'AWS_AVAILABILITY_ZONE')
        try:
            self.aws_key = config.get('s3', 'aws_access_key_id')
        except:
            self.aws_key = config.get_or_envvar('defaults', 'aws_access_key_id', 'AWS_ACCESS_KEY_ID')
        try:
            self.aws_secret = config.get('s3', 'aws_secret_access_key')
        except:
            self.aws_secret = config.get_or_envvar('defaults', 'aws_secret_access_key', 'AWS_SECRET_ACCESS_KEY')

    def send(self, id, name, filename):
        s3location = "s3://%s/%s/%s/%s" % (
            self.bucket,
            id,
            self.runtime.strftime("%Y%m%d%H%M%S"),
            os.path.basename(filename))
        logging.info("Uploading '%s' backup to S3 (%s)..." % (name, s3location))

        uploadargs = ['aws', 's3', 'cp', '--only-show-errors', filename, s3location]
        uploadproc = subprocess.Popen(uploadargs, stderr=subprocess.PIPE)
        uploadproc.wait()
        exitcode = uploadproc.returncode
        errmsg = uploadproc.stderr.read()
        if exitcode != 0:
            raise BackupException("Error while uploading: %s" % errmsg)

    def cleanup(self, id, name, stats):
        s3location = "s3://%s/%s" % (self.bucket, id)
        logging.info("Clearing down older '%s' backups from S3 (%s)..." % (name, s3location))

        # Gather list of potentials first
        s3conn = boto.s3.connect_to_region(self.az,
            aws_access_key_id=self.aws_key,
            aws_secret_access_key=self.aws_secret)
        bucket = s3conn.get_bucket(self.bucket)
        candidates = []
        for key in bucket.list(prefix=id):
            parsed_date = dateutil.parser.parse(key.last_modified)
            candidates.append([parsed_date, key.name])
        candidates.sort()

        # Loop and purge unretainable copies
        removable_names = []
        if self.retention_copies > 0:
            names = [name for d, name in candidates]
            if len(names) > self.retention_copies:
                removable_names = names[0:(len(names) - self.retention_copies)]
        if self.retention_days > 0:
            for d, name in candidates:
                days = (d - timedate.timedate.now()).days
                if days > self.retention_days:
                    removable_names.append(name)
        for name in removable_names:
            logging.info("Removing '%s'..." % name)
            bucket.get_key(name).delete()

        # Return number of copies left
        stats.retained_copies = len(candidates) - len(removable_names)