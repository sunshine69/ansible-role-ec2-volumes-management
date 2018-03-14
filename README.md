ansible-role-ec2-volumes-management
=========

Implement snapshot backup and cleanup.

This role will:
- Scan all volumes in the `regions` with tag Backup: yes and Status: in-use
- Then create a snapshot backup daily. Snapshot will be tag with the same 'Name' and a key 'Backup'

- Scan all snapshot in the `regions` with creation time longer than `retention_days` days with tag 'Name': '\*' and 'Backup': yes
- Then remove them except the last 1 backup

- Scan and remove all snapshots that was created by the AMI launch but AMI has already been de-registered.

Requirements
------------

- `aws_account_id` - Required - The account id that you want to scan for objects.

- `aws_profile_account` - Optional

  If you run without supplying the variable `profile` and `region` it will use a role
  `aws_profile_account` which will try to assume a IAM role
  `profile_account_role_arn` to obtain the permission to do the task.

- `ansible-role-aws-lambda` - Required. See https://github.com/willthames/ansible-role-aws-lambda

  This is to create the lambda function and the cloudwatch event to do run the
  python scripts which do the actual mainteance


Role Variables
--------------

- `regions` - Optional - A string with python syntax as a python list of all
  region you want to scan for volumes and snapshots.

  Default value is a list with one element taking the current variable `region`

- `retention_days` - Optional - Default: 7 - Number of days to keep snapshot.

- `lambda_scheduled_rule_expression` - Optional - Default: 'cron(0 1 \* \* ? \*)' (run daily)


Dependencies
------------


Example Playbook
----------------

```
- hosts: localhost
  vars:
    region: "ap-southeast-2"
    profile: "act2_non_prod"
  roles:
    - ec2-volumes-management
```

License
-------

BSD

Author Information
------------------

Steve Kieu, XVT Solutions (steve.kieu@xvt.com.au)
