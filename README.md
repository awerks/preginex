# Software engineering project

## Link to the demo website:

[softwareproject.up.railway.app](https://softwareproject.up.railway.app/)

## For admin rights, use the following credentials:

- **Username:** `admin`
- **Password:** `admin`

if you sign in with google, you'll have worker's access rights for now.

## Getting started with the project

### Clone the repository

```bash
git clone https://github.com/avalean07/se_project_1000 && cd se_project_1000
```

### Create conda environment

```bash
conda create -n se_project python=3.12 --file requirements.txt
```

## Set environment variables (provided in google docs)

```bash
conda env config vars set myvar=value
```

### Restart the conda environment

```bash
conda deactivate
conda activate se_project
```

### Run the server

```bash
flask run --debug
```

### Access the local server

The server can be accessed at [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

## P.S

Add your pictures to static/images in the format of `<team-memberX>.jpg`

## Deployment

The project is deployed at [Railway](https://railway.com/). Each time the code is pushed to the main branch, the website will be updated automatically.
