package controller;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Classe utility che mantiene l'elenco dei gestureId
 * per cui esiste un'animazione realmente eseguibile su Pepper.
 */
public final class PepperAnimatableGestures {

    /**
     * Insieme immutabile dei gestureId animabili.
     * LinkedHashSet preserva l'ordine di inserimento.
     */
    private static final Set<String> ANIMATABLE = Collections.unmodifiableSet(
            new LinkedHashSet<String>(Arrays.asList(
                    "ciao",
                    "acqua",
                    "casa",
                    "andare",
                    "bilancia",
                    "doccia",
                    "amare"
            ))
    );

    /**
     * Costruttore privato: la classe è solo utility e non va istanziata.
     */
    private PepperAnimatableGestures() {
        // Utility class
    }

    /**
     * Verifica se un gestureId è animabile su Pepper.
     * Normalizza il valore con trim + lowercase per maggiore robustezza.
     *
     * @param gestureId identificativo del gesto
     * @return true se il gesto è presente nell'elenco, false altrimenti
     */
    public static boolean isAnimatable(String gestureId) {
        if (gestureId == null) {
            return false;
        }
        return ANIMATABLE.contains(normalize(gestureId));
    }

    /**
     * Restituisce l'insieme dei gestureId animabili.
     * Il Set restituito è immutabile.
     */
    public static Set<String> list() {
        return ANIMATABLE;
    }

    /**
     * Normalizza il gestureId per confronti stabili.
     */
    private static String normalize(String value) {
        return value.trim().toLowerCase(Locale.ROOT);
    }
}
