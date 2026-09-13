package model;




public class ElementoMultimediale {
    private String nome;
    private String urlImmagine; // Contiene solo /media/Nome.ext
    private String urlVideo;    // Contiene solo /media/Nome.ext

    public ElementoMultimediale(String nome, String urlImmagine, String urlVideo) {
        this.nome = nome;
        this.urlImmagine = urlImmagine;
        this.urlVideo = urlVideo;
    }

    public String getNome() { return nome; }
    public String getUrlImmagine() { return urlImmagine; }
    public String getUrlVideo() { return urlVideo; }
}