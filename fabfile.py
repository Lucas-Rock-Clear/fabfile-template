from fabric import Connection, task
PROJECT_NAME = 'PROJECT_NAME' #important, folders and files on the server will be related to this name
REPO_URL = 'REPO_URL' #should be like 'git@github.com-reponame:RepoOwner/{Repo-name}.git'
BRANCH = "BRANCH" #the name of the branch
REMOTE_WORK_DIR = 'REMOTE_WORK_DIR' #Where on the server, should the repo be cloned(ensure it is an empty folder)
CELLERY_APP = "CELLERY_APP" #The name of the APP Celery has
VENV_PATH = f'{REMOTE_WORK_DIR}/venv' #Leave this as it is, unless strictly necessary.


def get_connection():
    return Connection(
        host='host-name', #whathever the host name you configured on etc/hosts that points to the server
    )

##bellow are the tasks you can call to execute the premade script, refrain to the documentation
@task
def deploy(c):
    conn = get_connection()

    print(f"Deploying branch: {BRANCH} from repo: {REPO_URL}")
    print(f"Remote working directory: {REMOTE_WORK_DIR}")
    print(f"Virtual environment path: {VENV_PATH}")

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run(f'git pull origin {BRANCH}')
    except Exception as e:
        print(f"Error pulling from repo: {e}")

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run('source venv/bin/activate && pip install -r requirements.txt')
    except Exception as e:
        print(f"Error installing requirements: {e}")

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run('source venv/bin/activate && python manage.py makemigrations')
    except Exception as e:
        print(f"Error making migrations: {e}")

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run('source venv/bin/activate && python manage.py migrate')
    except Exception as e:
        print(f"Error applying migrations: {e}")


    try:
        print("Restarting Nginx...")
        conn.run('sudo /opt/nginx/sbin/nginx -s stop')
        conn.run('sudo /opt/nginx/sbin/nginx')
    except Exception as e:
        print(f"Error restarting Nginx: {e}")    

@task
def setup(c):
    conn = get_connection()

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run(f'git clone {REPO_URL} .')
    except Exception as e:
        print(f"Error cloning repo: {e}")

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run(f'python3 -m venv {VENV_PATH}')
    except Exception as e:
        print(f'Error creating virtual environment: {e}')

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run('source venv/bin/activate && pip install -r requirements.txt')
    except Exception as e:
        print(f"Error installing requirements: {e}")

    try:
        with conn.cd(REMOTE_WORK_DIR):
            conn.run('source venv/bin/activate && python manage.py makemigrations')
            conn.run('source venv/bin/activate && python manage.py migrate')
    except Exception as e:
        print(f"Error applying migrations: {e}")
    
    try:
        gunicorn_service = create_gunicorn_service(PROJECT_NAME, REMOTE_WORK_DIR, VENV_PATH)
        celery_service = create_celery_service(PROJECT_NAME, REMOTE_WORK_DIR, VENV_PATH)
        #you could call more services that you want to use here.
        conn.run(f'echo "{gunicorn_service}" | sudo tee /etc/systemd/system/{PROJECT_NAME}_gunicorn.service')
        conn.run(f'echo "{celery_service}" | sudo tee /etc/systemd/system/{PROJECT_NAME}_celery.service')

        conn.run(f'sudo systemctl enable {PROJECT_NAME}_gunicorn')
        conn.run(f'sudo systemctl start {PROJECT_NAME}_gunicorn')
        conn.run(f'sudo systemctl enable {PROJECT_NAME}_celery')
        conn.run(f'sudo systemctl start {PROJECT_NAME}_celery')
    except Exception as e:
        print(f"Error creating systemd service files: {e}")


#Gunicorn daemon
def create_gunicorn_service(project_name, remote_work_dir, venv_path):
    return f"""
    [Unit]
    Description=gunicorn daemon for {project_name}
    After=network.target nginx.service
    Requires=nginx.service

    [Service]
    User=www-data
    Group=www-data
    WorkingDirectory={remote_work_dir}
    ExecStart={venv_path}/bin/gunicorn --workers 3 --bind 0.0.0.0:8080 {project_name}.wsgi:application

    [Install]
    WantedBy=multi-user.target
    """

#Celery daemon
def create_celery_service(project_name, remote_work_dir, venv_path):
    return f"""
    [Unit]
    Description=Celery daemon for Django project
    After=network.target nginx.service
    Requires=nginx.service

    [Service]
    User=www-data
    Group=www-data
    WorkingDirectory={remote_work_dir}
    Environment="PATH={venv_path}/bin"
    Environment="DJANGO_SETTINGS_MODULE={project_name}.settings"
    ExecStart={venv_path}/bin/celery -A {project_name} worker --loglevel=INFO

    [Install]
    WantedBy=multi-user.target
    """
