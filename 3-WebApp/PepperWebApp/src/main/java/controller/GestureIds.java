package controller;

import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Normalizzazione unica degli identificativi dei gesti, condivisa per convenzione
 * con il JavaScript (ps-core.js -> normalizeGestureId), con Controll
 * (utils.normalize_gesture_id) e con Process (_safe_slug, che da' il nome ai file):
 * minuscolo, accenti rimossi, ogni sequenza di caratteri non alfanumerici -> "_",
 * "_" iniziali e finali eliminati.  Esempi: "Università" -> "universita",
 * "Buon giorno!" -> "buon_giorno".
 */
public final class GestureIds {

    private static final Pattern MARKS = Pattern.compile("\\p{M}+");
    private static final Pattern NON_ALNUM = Pattern.compile("[^a-z0-9]+");
    private static final Pattern VALID_ID = Pattern.compile("^[a-z0-9_]{1,100}$");

    /** Parola scritta o riconosciuta a voce: lettere (anche accentate), numeri, spazi, apostrofo, trattino. */
    private static final Pattern VALID_WORD = Pattern.compile("^[\\p{L}\\p{N} _'\\u2019-]{1,100}$");

    private GestureIds() {
        // Utility class
    }

    public static String normalize(String value) {
        if (value == null) {
            return "";
        }
        String s = Normalizer.normalize(value.trim().toLowerCase(Locale.ROOT), Normalizer.Form.NFKD);
        s = MARKS.matcher(s).replaceAll("");
        s = NON_ALNUM.matcher(s).replaceAll("_");
        int start = 0;
        int end = s.length();
        while (start < end && s.charAt(start) == '_') {
            start++;
        }
        while (end > start && s.charAt(end - 1) == '_') {
            end--;
        }
        return s.substring(start, end);
    }

    /** true se l'id e' gia' normalizzato e sicuro da usare in comandi e nomi di file. */
    public static boolean isValidId(String id) {
        return id != null && VALID_ID.matcher(id).matches();
    }

    /** true se la parola puo' essere inviata al servizio Process. */
    public static boolean isValidWord(String word) {
        return word != null && VALID_WORD.matcher(word.trim()).matches() && isValidId(normalize(word));
    }
}
