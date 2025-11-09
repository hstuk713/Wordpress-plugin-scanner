# Set Docker
sudo docker pull mysql:5.7
sudo docker pull wordpress

sudo docker run -d --name mysql_db \
  -e MYSQL_ROOT_PASSWORD=toor \
  -e MYSQL_DATABASE=wpdb \
  -e MYSQL_USER=wp \
  -e MYSQL_PASSWORD=wppass \
  -v mysql:/var/lib/mysql \
  mysql:5.7

sudo docker run -d --name wp \
  -p 8080:80 \
  --link mysql_db:wpdb \
  -e WORDPRESS_DB_HOST=wpdb \
  -e WORDPRESS_DB_USER=wp \
  -e WORDPRESS_DB_PASSWORD=wppass \
  -e WORDPRESS_DB_NAME=wpdb \
  -v wp:/var/www/html \
  wordpress
<br>
