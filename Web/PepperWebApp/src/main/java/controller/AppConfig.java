package controller;

import java.io.File;

/**
 * Configurazione centralizzata della WebApp.
 *
 * Ogni valore viene letto, in ordine di priorita':
 *   1. variabile d'ambiente (usata da Docker / docker-compose)
 *   2. proprieta' di sistema JVM (-Dnome=valore)
 *   3. valore di default (compatibile con il setup locale precedente)
 *
 * Variabili supportate:
 *   PEPPERSIGN_PROCESS_URL  URL base del servizio Flask (default http://127.0.0.1:5000)
 *   PEPPERSIGN_DATA_DIR     cartella condivisa dei media   (default ~/PepperSignData)
 */
public final class AppConfig {

    public static final String ENV_PROCESS_URL = "PEPPERSIGN_PROCESS_URL";
    public static final String ENV_DATA_DIR = "PEPPERSIGN_DATA_DIR";

    private static final String DEFAULT_PROCESS_URL = "http://127.0.0.1:5000";
    private static final String DEFAULT_DATA_DIR =
            System.getProperty("user.home") + File.separator + "PepperSignData";

    private AppConfig() {
        // Utility class
    }

    /** URL base del servizio Python (senza slash finale). */
    public static String processBaseUrl() {
        String value = read(ENV_PROCESS_URL, DEFAULT_PROCESS_URL);
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    /** URL completo di un endpoint del servizio Python, es. processUrl("/process"). */
    public static String processUrl(String path) {
        if (path == null || path.isEmpty()) {
            return processBaseUrl();
        }
        return processBaseUrl() + (path.startsWith("/") ? path : "/" + path);
    }

    /** Cartella condivisa con il modulo Process (video e immagini degli scheletri). */
    public static String dataDir() {
        return read(ENV_DATA_DIR, DEFAULT_DATA_DIR);
    }

    private static String read(String name, String fallback) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            value = System.getProperty(name);
        }
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        return value.trim();
    }
}
