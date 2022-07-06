# cmr-pgstac-loader
AWS stack to ingest HLS STAC metadata into a pgstac instance with batched streaming.
Also includes utilities to query CMR to ingest a subset of HLS granules.

![architecture](docs/architecture.png)

## Requirements
- Python==3.8
- Docker
- tox
- aws-cli
- An IAM role with sufficient permissions for creating, destroying and modifying the relevant stack resources.

## Environment Settings
```
$ export STACKNAME=<Name of your stack>
$ export PROJECT=<The project name for resource cost tracking>
$ export SECRET_NAME=<The ARN of the secret where the target pgstac db credentials are stored>
```

## CDK Commands
### Synth
Display generated cloud formation template that will be used to deploy.
```
$ tox -e dev -r -- synth
```

### Diff
Display a diff of the current deployment and any changes created.
```
$ tox -e dev -r -- diff || true
```

### Deploy
Deploy current version of stack.
```
$ tox -e dev -r -- deploy
```

## Development
For active stack development run
```
$ tox -e dev -r -- version
```
This creates a local virtualenv in the directory `devenv`.  To use it for development
```
$ source devenv/bin/activate
```
Then run the following to install the project's pre-commit hooks
```
$ pre-commit install
```

## Tests
To run unit test for all included Lambda functions
```
tox -r
```
