==========================
 Serverless Stepfunctions
==========================

Implement the AWS Trouble Ticket Step Functions example using the the
Serverless Framework and plugin. And we'll switch from Node to Python.

I'm using node v12.2.0. Install serverless woth step functions and AWS
pseudo param plugins::

  npm install

The serverless app is under ``slssteps`` so::

  cd slssteps

The ``package.json`` installs serverless locally, not globally, so you
don't have the binary in your PATH. You could set path or do::

  alias sls=../node_modules/.bin/sls

Provide your AWS creds::

  export AWS_PROFILE=vstudios

Deploy the lambdas, workflow, other resources::

  sls deploy

You can test a function and see its logs::

  sls invoke -f hello -l

We have functions mirroring the AWS example:
* OpenCase
* AssignCase
* WorkOnCase
* EscalateCase
* CloseCase

We can invoke the OpenCase to test it in isolation, or to start the
Step Function state machine once it's defined::

  sls invoke -f OpenCase -l -d '{"input_case_id": "42"}'
