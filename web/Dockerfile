FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY index.html config.js girando-api.js girando-photo.js support.js fonts.css /usr/share/nginx/html/
COPY css /usr/share/nginx/html/css
COPY admin /usr/share/nginx/html/admin
COPY assets /usr/share/nginx/html/assets
COPY fonts /usr/share/nginx/html/fonts
COPY vendor /usr/share/nginx/html/vendor
EXPOSE 8080
