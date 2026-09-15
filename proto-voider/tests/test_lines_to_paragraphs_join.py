"""F9's "line cojoiner" sólo une líneas que terminan en , o en un signo de
cierre de oración — no cualquier cosa.

Federico: "in f9, right now it cojoins lines. It should only do that when the
lines end in , or a dot."

Antes lines_to_paragraphs pegaba con un espacio TODAS las líneas consecutivas
de un grupo de punto, sin mirar qué tenían adentro. Para prosa reformateada
(una oración por línea, cada una ya termina en . ? ! …) eso reconstruye el
párrafo bien. Pero para scriptio continua —fragmentos sin puntuación
ninguna— hacía exactamente lo mismo: pegaba todo en una sola línea gigante.
Ése era el bug de fusión de F9.

Ahora sólo se pega la línea siguiente si la ANTERIOR termina en algo que
cierra: no sólo "," y "." como pidió textualmente, sino el mismo conjunto que
ya usa el resto del código para "esto es el final de una oración"
(f2_mixin.SENTENCE_ENDERS = '.?!…'), con la coma sumada. Ampliar de ",." a
",.?!…" no es capricho: lines_to_paragraphs también arma el documento de F4 y
el PDF (build_reading_document, reading_page.py:171) — el texto de VERDAD del
libro. Con sólo "," y "." al pie de la letra, cualquier párrafo real que
tuviera una pregunta o una exclamación en el medio se partiría en dos al
exportar, porque split_sentences termina las oraciones en .?!… y ninguna de
esas líneas terminaría en coma o punto.
"""
import reading_page as rp


class TestJoinsOnlyOnSentenceEnders:

    def test_unpunctuated_fragments_stay_separate(self):
        """El caso que rompía: scriptio continua, cero puntuación."""
        assert rp.lines_to_paragraphs(['uno', 'dos', 'tres']) == [
            'uno', 'dos', 'tres']

    def test_a_dot_ended_line_joins_the_next(self):
        assert rp.lines_to_paragraphs(['Uno.', 'Dos.']) == ['Uno. Dos.']

    def test_a_comma_ended_line_joins_the_next(self):
        assert rp.lines_to_paragraphs(['uno,', 'dos.']) == ['uno, dos.']

    def test_a_question_mark_also_joins(self):
        """No es sólo lo que Federico dijo literal — ver el docstring del
        archivo: hace falta para no romper F4/PDF con preguntas mid-párrafo."""
        assert rp.lines_to_paragraphs(['¿Uno?', 'Dos.']) == ['¿Uno? Dos.']

    def test_an_exclamation_also_joins(self):
        assert rp.lines_to_paragraphs(['¡Uno!', 'Dos.']) == ['¡Uno! Dos.']

    def test_an_ellipsis_also_joins(self):
        assert rp.lines_to_paragraphs(['Uno…', 'Dos.']) == ['Uno… Dos.']

    def test_mixed_within_one_dot_group(self):
        """Fragmentos sin puntuación quedan sueltos, la oración bien formada
        se pega — conviven en el mismo grupo de punto."""
        assert rp.lines_to_paragraphs(
            ['fragmento', 'suelto', 'Una oración.', 'que sigue.']) == [
            'fragmento', 'suelto', 'Una oración. que sigue.']

    def test_a_dot_separator_still_breaks_regardless_of_punctuation(self):
        """El separador de párrafo manda siempre, aunque la última línea
        terminara en algo que "pegaría"."""
        assert rp.lines_to_paragraphs(['Uno.', '.', 'Dos.']) == ['Uno.', 'Dos.']

    def test_leading_and_double_dots(self):
        assert rp.lines_to_paragraphs(['.', 'Uno.', '.', '.', 'Dos.']) == [
            'Uno.', 'Dos.']

    def test_o_marker_and_blanks_ignored(self):
        assert rp.lines_to_paragraphs(['ø', 'Uno.', '', 'Dos.']) == ['Uno. Dos.']

    def test_empty(self):
        assert rp.lines_to_paragraphs([]) == []
        assert rp.lines_to_paragraphs(['.', '.']) == []

    def test_a_single_unpunctuated_line_is_its_own_paragraph(self):
        assert rp.lines_to_paragraphs(['solo']) == ['solo']


class TestRealFusionCase:
    """La reproducción del bug real, tal como está documentado en pending.txt:
    una línea de 3204 caracteres de scriptio continua que F9 fundía entera."""

    def test_the_real_fragment_survives_unfused(self):
        frags = ['ICANNOTSTOPLUSTINGFOROTHERWOMEN', 'ILUSTFOREVERYWOMANIMEET',
                 'ISEETHEBEAUTYINTHEM']
        assert rp.lines_to_paragraphs(frags) == frags   # ninguna fusión

    def test_properly_reformatted_prose_is_unaffected(self):
        """El caso normal — capítulos reales, una oración por línea — sigue
        reconstruyendo el párrafo entero como siempre."""
        lines = ['La primera oración del párrafo.',
                 '¿Y la segunda, una pregunta?',
                 '¡La tercera, una exclamación!',
                 'La cuarta cierra normal.']
        assert rp.lines_to_paragraphs(lines) == [' '.join(lines)]
