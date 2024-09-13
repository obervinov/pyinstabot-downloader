# /bin/bash
# Description: Prepare psql for pyinstabot-downloader
NEW_USER_PASSWORD=$(pwgen 24 -c1)
psql -c "CREATE DATABASE pyinstabot-downloader;"
psql -c "CREATE USER pyinstabot-downloader WITH PASSWORD '$NEW_USER_PASSWORD';"
psql -c "ALTER DATABASE pyinstabot-downloader OWNER TO pyinstabot-downloader;"
echo "New user: pyinstabot-downloader"
echo "New password: $NEW_USER_PASSWORD"
echo "Database: pyinstabot-downloader"
# End of snippet
