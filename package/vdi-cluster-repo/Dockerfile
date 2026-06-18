FROM nginx:alpine
COPY charts/ /usr/share/nginx/html/charts/
RUN cd /usr/share/nginx/html/charts && \
    [ -f index.yaml ] || helm repo index .
EXPOSE 80
