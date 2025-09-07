# Gitpy: a Git client written in Python

This repository is for the Gitpy source code pushed with git bash, if you want to see a repository pushed with Gitpy itself, check out my gitpy_test repository.

## How to push your own repository

1. Set you system environment variables appropraitely (or modify the script to just include them). The variables which need to be added are: GIT_USERNAME (your github username), GIT_PASSWORD (Not your password, but a personal access token), GIT_AUTHOR_NAME (your name), GIT_AUTHOR_EMAIL (your github email address)

2. Place gitpy.py outside of where you would like to create the repository (repository creation in the same folder is not yet implemented). Navigate to gitpy.py in your terminal of choice and run `py gitpy.py init gitpy` (if you want to create a gitpy repository)

3. Copy the files (including gitpy.py itself!) over to the new repository folder, for me, it was gitpy.py itself. Open the repository in the terminal then run `py gitpy.py add filename` for each file added (in my case, just gitpy.py itself `py gitpy.py add gitpy.py`)

4. Git commit and add a message like so `py gitpy.py commit -m "if you see this, gitpy works!"`

5. Finally push to your main branch like so, `py gitpy.py push https://github.com/git_username/repo_name.git`. The client uses the previously defined environment variables as credentials to push to the repository.