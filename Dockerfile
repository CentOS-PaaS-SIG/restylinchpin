FROM fedora:30
MAINTAINER Mansi Kulkarni "mankulka@redhat.com"
RUN apt-get update -y
RUN apt-get install -y python3-pip python3-dev build-essential
COPY . /app
WORKDIR /app
RUN pip3 install -r req uirements.txt
ENTRYPOINT ["python3"]
CMD ["app.py"]x