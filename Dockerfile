FROM fedora:30
MAINTAINER Mansi Kulkarni "mankulka@redhat.com"
RUN dnf -y install python3-pip python3-devel && dnf clean all
COPY . /app
WORKDIR /app
RUN pip3 install -r requirements.txt
ENTRYPOINT ["python3"]
CMD ["__init__.py"]