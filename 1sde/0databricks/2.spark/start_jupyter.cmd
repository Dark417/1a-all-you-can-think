@echo off
rem Launch JupyterLab from the project venv.
rem (The notebook's first cell sets JAVA_HOME / HADOOP_HOME / PYSPARK_PYTHON itself,
rem  so no environment setup is needed here.)
cd /d "%~dp0"
".venv\Scripts\python.exe" -m jupyterlab spark_tutorial.ipynb
