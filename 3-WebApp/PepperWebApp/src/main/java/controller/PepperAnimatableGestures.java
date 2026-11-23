package controller;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Elenco dei gestureId eseguibili su Pepper, letto dalla cartella dei gesti
 * registrati con Controll (PEPPERSIGN_GESTURES_DIR, in Docker /data/gestures).
 *
 * La chiave di ogni file e' la stessa usata da Controll (GestureStore._derive_key):
 * "gesture_id", altrimenti "name", altrimenti il nome del file, normalizzata con
 * {@link GestureIds#normalize}. La cartella viene riletta al massimo ogni 2 s,
 * cosi' un gesto appena salvato diventa disponibile senza riavviare la WebApp.
 * Se la cartella non esiste si usa l'elenco fisso di prima.
 */
public final class PepperAnimatableGestures {

    private static final List<String> FALLBACK = Arrays.asList(
            "ciao", "acqua", "casa", "andare", "bilancia", "doccia", "amare");

    /** Gesti "tecnici" (generati in automatico, versioni di prova): eseguibili ma senza card nel catalogo. */
    private static final Pattern HIDDEN_FROM_CATALOG = Pattern.compile("^gesto_\\d.*|.*_auto$|.*v\\d+$");

    private static final long RESCAN_MS = 2000L;

    private static final Object LOCK = new Object();
    private static long lastScan = 0L;
    private static long lastSignature = Long.MIN_VALUE;
    private static Map<String, Map<String, Object>> cache = Collections.emptyMap();

    private PepperAnimatableGestures() {
        // Utility class
    }

    public static boolean isAnimatable(String gestureId) {
        return gestureId != null && entries().containsKey(GestureIds.normalize(gestureId));
    }

    /** Insieme (immutabile) dei gestureId eseguibili. */
    public static Set<String> list() {
        return Collections.unmodifiableSet(new LinkedHashSet<String>(entries().keySet()));
    }

    /** Dettagli dei gesti: id, nome da mostrare, presenza nel catalogo. */
    public static List<Map<String, Object>> details() {
        return new ArrayList<Map<String, Object>>(entries().values());
    }

    private static Map<String, Map<String, Object>> entries() {
        synchronized (LOCK) {
            long now = System.currentTimeMillis();
            if (now - lastScan < RESCAN_MS && lastScan != 0L) {
                return cache;
            }
            lastScan = now;
            File dir = new File(AppConfig.gesturesDir());
            File[] files = dir.isDirectory() ? dir.listFiles() : null;
            if (files == null) {
                if (lastSignature != -1L) {
                    cache = fallback();
                    lastSignature = -1L;
                }
                return cache;
            }
            long signature = dir.lastModified() * 31L + files.length;
            for (File f : files) {
                signature = signature * 31L + f.lastModified() + f.length();
            }
            if (signature != lastSignature) {
                cache = scan(files);
                lastSignature = signature;
            }
            return cache;
        }
    }

    private static Map<String, Map<String, Object>> scan(File[] files) {
        Arrays.sort(files, Comparator.comparing(File::getName));   // stesso ordine di Controll: vince l'ultimo
        Map<String, Map<String, Object>> out = new LinkedHashMap<String, Map<String, Object>>();
        for (File f : files) {
            String fileName = f.getName();
            if (!f.isFile() || !fileName.toLowerCase(Locale.ROOT).endsWith(".json")) {
                continue;
            }
            try {
                String text = new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8);
                JsonElement root = JsonParser.parseString(text);
                if (!root.isJsonObject()) {
                    continue;
                }
                JsonObject obj = root.getAsJsonObject();
                String baseName = fileName.substring(0, fileName.length() - 5);
                String id = GestureIds.normalize(firstNonEmpty(str(obj, "gesture_id"), str(obj, "name"), baseName));
                if (!GestureIds.isValidId(id)) {
                    continue;
                }
                Map<String, Object> entry = new LinkedHashMap<String, Object>();
                entry.put("id", id);
                entry.put("name", displayName(obj, id));
                entry.put("catalog", !HIDDEN_FROM_CATALOG.matcher(id).matches());
                out.remove(id);
                out.put(id, entry);
            } catch (IOException | RuntimeException e) {
                // file non leggibile o JSON non valido: ignorato (come in Controll)
            }
        }
        return out;
    }

    /** "display_name" se presente; altrimenti "name" se corrisponde all'id; altrimenti l'id leggibile. */
    private static String displayName(JsonObject obj, String id) {
        String display = str(obj, "display_name");
        if (!display.isEmpty()) {
            return display;
        }
        String name = str(obj, "name");
        if (!name.isEmpty() && GestureIds.normalize(name).equals(id)) {
            return name;
        }
        String text = id.replace('_', ' ');
        return text.isEmpty() ? id : Character.toUpperCase(text.charAt(0)) + text.substring(1);
    }

    private static Map<String, Map<String, Object>> fallback() {
        Map<String, Map<String, Object>> out = new LinkedHashMap<String, Map<String, Object>>();
        for (String id : FALLBACK) {
            Map<String, Object> entry = new LinkedHashMap<String, Object>();
            entry.put("id", id);
            entry.put("name", Character.toUpperCase(id.charAt(0)) + id.substring(1));
            entry.put("catalog", true);
            out.put(id, entry);
        }
        return out;
    }

    private static String str(JsonObject obj, String key) {
        JsonElement el = obj.get(key);
        if (el == null || el.isJsonNull() || !el.isJsonPrimitive()) {
            return "";
        }
        return el.getAsString().trim();
    }

    private static String firstNonEmpty(String... values) {
        for (String v : values) {
            if (v != null && !v.trim().isEmpty()) {
                return v;
            }
        }
        return "";
    }
}
