# Wordpress-plugin-scanner

## Set Docker
sudo docker pull mysql:5.7 <br>
sudo docker pull wordpress<br>

sudo docker run -d --name mysql_db<br>
-e MYSQL_ROOT_PASSWORD=toor<br>
-e MYSQL_DATABASE=wpdb<br>
-e MYSQL_USER=wp<br>
-e MYSQL_PASSWORD=wppass<br>
-v mysql:/var/lib/mysql<br>
mysql:5.7<br>

sudo docker run -d --name wp<br>
-p 8080:80<br>
--link mysql_db:wpdb<br>
-e WORDPRESS_DB_HOST=wpdb<br>
-e WORDPRESS_DB_USER=wp<br>
-e WORDPRESS_DB_PASSWORD=wppass<br>
-e WORDPRESS_DB_NAME=wpdb<br>
-v wp:/var/www/html<br>
wordpress<br>
