# ==========================================================
# PepperSign - Web (Tomcat 10.1 + Java 17)
# Build multi-stage: Maven compila il WAR, Tomcat lo esegue.
# L'app viene pubblicata su /PepperSign (il JavaScript ricava
# il context path dal primo segmento dell'URL).
# ==========================================================

# ---------- 1) Build ----------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src

# Scarico prima le dipendenze: vengono messe in cache finche' pom.xml non cambia.
COPY pom.xml .
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -q package -DskipTests \
 && cp target/*.war /src/PepperSign.war

# ---------- 2) Runtime ----------
FROM tomcat:10.1-jdk17-temurin

# Rimuovo le webapp di esempio di Tomcat.
RUN rm -rf /usr/local/tomcat/webapps/*

COPY --from=build /src/PepperSign.war /usr/local/tomcat/webapps/PepperSign.war

# Valori di default pensati per docker-compose (sovrascrivibili da .env).
ENV PEPPERSIGN_DATA_DIR=/data/media \
    PEPPERSIGN_PROCESS_URL=http://process:5000 \
    TZ=Europe/Rome

VOLUME ["/data/media"]
EXPOSE 8080

CMD ["catalina.sh", "run"]
