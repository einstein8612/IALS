# Docker image
FROM python:3.6.15-slim-bullseye

# Install requirements
RUN apt-get update -y && \
    apt-get install -y git cmake python3 g++ libxerces-c-dev libfox-1.6-dev libgdal-dev libproj-dev libgl2ps-dev python3-dev swig default-jdk maven libeigen3-dev

RUN apt-get install -y sumo sumo-tools sumo-doc

# Working directory
WORKDIR /app
COPY . /app

# Install Python requirements
COPY Pipfile Pipfile.lock ./
RUN python -m pip install --upgrade pip
RUN pip install pipenv && pipenv install --system --dev

# # Clone and build SUMO repository
# RUN git clone --recursive https://github.com/eclipse/sumo && \
#     cd ./sumo && \
#     mkdir -p build/cmake-build && \
#     cd build/cmake-build && \
#     cmake ../.. && \
#     make -j$(nproc)

# Clone additional repositories
RUN git clone https://github.com/INFLUENCEorg/flow.git && \
    git clone https://github.com/miguelsuau/recurrent_policies.git

RUN pip install -e ./flow && \
    pip install -e ./simulators/warehouse/ && \
    pip install -e ./simulators/traffic/

RUN chmod -R 777 ./flow/

# ENV SUMO_HOME="/app/sumo"
ENV PATH="${SUMO_HOME}/bin:${PATH}"

CMD ["python", "./experiment.py"]
# CMD ["bash"]