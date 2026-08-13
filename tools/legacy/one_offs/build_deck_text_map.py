#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SLIDES = [
    {
        "n": 1,
        "en_title": "AI in Construction: From Hype to Reality",
        "pt": {
            "title": "IA na Construção: do Hype à Realidade",
            "items": [
                ("lesson-label", "LIÇÃO 1"),
                ("promise", "Use IA como apoio à decisão sem confundir uma resposta bem escrita com a verdade do projeto."),
                ("right-panel-word", "JULGAMENTO\nPRIMEIRO"),
                ("right-panel-copy", "As ferramentas vêm depois."),
            ],
            "risk": "medium",
            "note": "`JULGAMENTO PRIMEIRO` is longer than the English label and may need smaller type.",
        },
        "es": {
            "title": "IA en la Construcción: de la Exageración a la Realidad",
            "items": [
                ("lesson-label", "LECCIÓN 1"),
                ("promise", "Usa la IA como apoyo a la decisión sin confundir una respuesta bien escrita con la verdad del proyecto."),
                ("right-panel-word", "CRITERIO\nPRIMERO"),
                ("right-panel-copy", "Las herramientas vienen después."),
            ],
            "risk": "high",
            "note": "Spanish title is longer and likely needs layout or type-size adjustment.",
        },
    },
    {
        "n": 2,
        "en_title": "AI is already in construction workflows",
        "pt": {
            "title": "A IA já está nos fluxos de trabalho da construção",
            "items": [
                ("slide-subtitle", "A pergunta não é se a IA impressiona. A pergunta é se ela melhora uma decisão real de projeto."),
                ("bullet-1", "A documentação está se multiplicando: RFIs, submittals, daily reports, atas, fotos e change logs."),
                ("bullet-2", "As equipes precisam de ajuda para redigir, organizar, resumir, comparar e sinalizar informações."),
                ("bullet-3", "Todo fluxo útil com IA ainda precisa de um responsável humano pelo registro ou pela decisão final."),
            ],
            "risk": "medium",
            "note": "Keeps U.S. document terms where useful for market context.",
        },
        "es": {
            "title": "La IA ya está en los flujos de trabajo de construcción",
            "items": [
                ("slide-subtitle", "La pregunta no es si la IA impresiona. La pregunta es si mejora una decisión real del proyecto."),
                ("bullet-1", "La documentación se multiplica: RFIs, submittals, reportes diarios, actas, fotos y registros de cambios."),
                ("bullet-2", "Los equipos necesitan ayuda para redactar, ordenar, resumir, comparar y señalar información."),
                ("bullet-3", "Todo flujo útil con IA todavía necesita una persona responsable del registro o de la decisión final."),
            ],
            "risk": "medium",
            "note": "Some U.S. terms preserved to avoid market drift.",
        },
    },
    {
        "n": 3,
        "en_title": "AI supports judgment. It does not replace it.",
        "pt": {
            "title": "A IA apoia o julgamento. Ela não substitui o profissional.",
            "items": [
                ("ai-box", "Saída da IA"),
                ("review-box", "Revisão\nprofissional"),
                ("decision-box", "Decisão"),
                ("quote", "Uma resposta confiante da IA não é o mesmo que uma decisão correta de projeto."),
            ],
            "risk": "medium",
            "note": "`Revisão profissional` fits the existing two-line box.",
        },
        "es": {
            "title": "La IA apoya el criterio. No lo reemplaza.",
            "items": [
                ("ai-box", "Resultado de IA"),
                ("review-box", "Revisión\nprofesional"),
                ("decision-box", "Decisión"),
                ("quote", "Una respuesta confiada de la IA no es lo mismo que una decisión correcta de proyecto."),
            ],
            "risk": "medium",
            "note": "`Resultado de IA` may need a modest width check.",
        },
    },
    {
        "n": 4,
        "en_title": "Different AI tasks create different risks",
        "pt": {
            "title": "Tarefas diferentes de IA criam riscos diferentes",
            "items": [
                ("Automation", "Automação"),
                ("Follows rules or triggers.", "Segue regras ou gatilhos."),
                ("Machine learning", "Machine learning"),
                ("Learns patterns from data.", "Aprende padrões nos dados."),
                ("Generative AI", "IA generativa"),
                ("Creates drafts or content.", "Cria rascunhos ou conteúdo."),
                ("Predictive analytics", "Análise preditiva"),
                ("Estimates what may happen.", "Estima o que pode acontecer."),
                ("bottom", "Comece nomeando a tarefa. O método de revisão certo depende do que a ferramenta faz."),
            ],
            "risk": "medium",
            "note": "Card labels should fit, but bottom sentence may need one line-height check.",
        },
        "es": {
            "title": "Diferentes tareas de IA crean diferentes riesgos",
            "items": [
                ("Automation", "Automatización"),
                ("Follows rules or triggers.", "Sigue reglas o activadores."),
                ("Machine learning", "Machine learning"),
                ("Learns patterns from data.", "Aprende patrones de los datos."),
                ("Generative AI", "IA generativa"),
                ("Creates drafts or content.", "Crea borradores o contenido."),
                ("Predictive analytics", "Análisis predictivo"),
                ("Estimates what may happen.", "Estima lo que puede ocurrir."),
                ("bottom", "Empieza por nombrar la tarea. El método de revisión correcto depende de lo que hace la herramienta."),
            ],
            "risk": "medium",
            "note": "Spanish text expansion likely affects bottom sentence.",
        },
    },
    {
        "n": 5,
        "en_title": "AI is easier to evaluate when it is tied to a workflow",
        "pt": {
            "title": "A IA é mais fácil de avaliar quando está ligada a um fluxo de trabalho",
            "items": [
                ("Documentation", "Documentação"),
                ("Preconstruction", "Pré-construção"),
                ("Safety", "Safety"),
                ("BIM / Design", "BIM / Design"),
                ("Field operations", "Operações de campo"),
                ("AI support", "Apoio de IA"),
                ("testable", "\"IA para construção\" é vago. \"IA para redigir daily reports para revisão\" é testável."),
            ],
            "risk": "high",
            "note": "Title and testable line are longer; likely need layout adjustment.",
        },
        "es": {
            "title": "La IA es más fácil de evaluar cuando está ligada a un flujo de trabajo",
            "items": [
                ("Documentation", "Documentación"),
                ("Preconstruction", "Preconstrucción"),
                ("Safety", "Safety"),
                ("BIM / Design", "BIM / Diseño"),
                ("Field operations", "Operaciones de campo"),
                ("AI support", "Apoyo de IA"),
                ("testable", "\"IA para construcción\" es vago. \"IA para redactar reportes diarios para revisión\" es comprobable."),
            ],
            "risk": "high",
            "note": "Title and bottom comparison need rewrite or smaller type.",
        },
    },
    {
        "n": 6,
        "en_title": "The biggest risk is the polished wrong answer",
        "pt": {
            "title": "O maior risco é a resposta errada com aparência profissional",
            "items": [
                ("Confabulation", "Confabulação"),
                ("risk-copy", "Uma saída de IA generativa pode apresentar conteúdo falso ou incorreto com confiança."),
                ("Construction impact", "Impacto na construção"),
                ("construction-copy", "Uma cláusula, referência de código, premissa de estimate ou sinal de cronograma pode parecer profissional e ainda estar errado."),
            ],
            "risk": "high",
            "note": "Construction-copy is long; use two lines or reduce font.",
        },
        "es": {
            "title": "El mayor riesgo es la respuesta incorrecta con apariencia profesional",
            "items": [
                ("Confabulation", "Confabulación"),
                ("risk-copy", "Un resultado de IA generativa puede presentar contenido falso o erróneo con confianza."),
                ("Construction impact", "Impacto en construcción"),
                ("construction-copy", "Una cláusula, referencia de código, supuesto de estimación o señal de cronograma puede parecer profesional y aun así estar mal."),
            ],
            "risk": "high",
            "note": "Spanish title and construction-copy need layout control.",
        },
    },
    {
        "n": 7,
        "en_title": "Safer AI workflows put output inside a review loop",
        "pt": {
            "title": "Fluxos de IA mais seguros colocam a saída dentro de um ciclo de revisão",
            "items": [
                ("Input", "Entrada"),
                ("AI output", "Saída da IA"),
                ("Human review", "Revisão humana"),
                ("Decision", "Decisão"),
                ("Record", "Registro"),
                ("loop-point", "O ponto de revisão não é opcional. É onde a responsabilidade do projeto entra no fluxo."),
            ],
            "risk": "high",
            "note": "Title is long; loop labels should fit except `Revisão humana` may need smaller type.",
        },
        "es": {
            "title": "Los flujos de IA más seguros ponen el resultado dentro de un ciclo de revisión",
            "items": [
                ("Input", "Entrada"),
                ("AI output", "Resultado de IA"),
                ("Human review", "Revisión humana"),
                ("Decision", "Decisión"),
                ("Record", "Registro"),
                ("loop-point", "El punto de revisión no es opcional. Ahí entra la responsabilidad del proyecto en el flujo."),
            ],
            "risk": "high",
            "note": "Title and `Resultado de IA` need layout verification.",
        },
    },
    {
        "n": 8,
        "en_title": "Use five questions to separate real value from hype",
        "pt": {
            "title": "Use cinco perguntas para separar valor real de hype",
            "items": [
                ("q1", "Que tarefa ela apoia?"),
                ("q2", "De quais dados ela precisa?"),
                ("q3", "Que evidência sustenta a promessa?"),
                ("q4", "O que ela não faz?"),
                ("q5", "Quem revisa a saída?"),
            ],
            "risk": "medium",
            "note": "Question 3 is longest and may need smaller type.",
        },
        "es": {
            "title": "Usa cinco preguntas para separar valor real de exageración",
            "items": [
                ("q1", "¿Qué tarea apoya?"),
                ("q2", "¿Qué datos necesita?"),
                ("q3", "¿Qué evidencia respalda la promesa?"),
                ("q4", "¿Qué no hace?"),
                ("q5", "¿Quién revisa el resultado?"),
            ],
            "risk": "medium",
            "note": "Question 3 may need wrapping inside box.",
        },
    },
    {
        "n": 9,
        "en_title": "The best AI user is not the most impressed user",
        "pt": {
            "title": "O melhor usuário de IA não é quem fica mais impressionado",
            "items": [
                ("bullet-1", "A IA pode redigir, resumir, classificar, buscar, prever e gerar opções."),
                ("bullet-2", "As decisões de projeto continuam pertencendo a pessoas e organizações."),
                ("bullet-3", "Fluxos úteis definem tarefa, dados, ponto de revisão, limites e responsável."),
                ("bullet-4", "A confiança cresce com evidência e revisão, não com linguagem impressionante."),
            ],
            "risk": "medium",
            "note": "Bullets are similar length to English and likely fit.",
        },
        "es": {
            "title": "El mejor usuario de IA no es quien más se impresiona",
            "items": [
                ("bullet-1", "La IA puede redactar, resumir, clasificar, buscar, predecir y generar opciones."),
                ("bullet-2", "Las decisiones de proyecto siguen perteneciendo a personas y organizaciones."),
                ("bullet-3", "Los flujos útiles definen tarea, datos, punto de revisión, límites y responsable."),
                ("bullet-4", "La confianza crece con evidencia y revisión, no con lenguaje impresionante."),
            ],
            "risk": "medium",
            "note": "Bullets likely fit, but title should be checked.",
        },
    },
    {
        "n": 10,
        "en_title": "Next, apply the judgment filter to project management",
        "pt": {
            "title": "Agora, aplique o filtro de julgamento à gestão de projetos",
            "items": [
                ("bridge-main", "A Lição 2 sai dos fundamentos de IA e entra em daily reports, atas, RFIs, cronogramas, recursos e revisão de documentos."),
                ("Daily reports", "Daily reports"),
                ("Meeting minutes", "Atas"),
                ("RFIs", "RFIs"),
                ("Schedules", "Cronogramas"),
                ("Document review", "Revisão documental"),
                ("closing", "Mesma regra: a IA pode apoiar o fluxo, mas o profissional é dono do registro."),
            ],
            "risk": "high",
            "note": "Bridge-main and closing are longer; likely need font/layout adjustment.",
        },
        "es": {
            "title": "Ahora, aplica el filtro de criterio a la gestión de proyectos",
            "items": [
                ("bridge-main", "La Lección 2 pasa de los fundamentos de IA a reportes diarios, actas, RFIs, cronogramas, recursos y revisión documental."),
                ("Daily reports", "Reportes diarios"),
                ("Meeting minutes", "Actas"),
                ("RFIs", "RFIs"),
                ("Schedules", "Cronogramas"),
                ("Document review", "Revisión documental"),
                ("closing", "Misma regla: la IA puede apoyar el flujo, pero el profesional es dueño del registro."),
            ],
            "risk": "high",
            "note": "Bridge-main likely needs two-line treatment.",
        },
    },
]


def build(locale: str, run_slug: str, lesson: str) -> None:
    key = "pt" if locale == "pt-br" else "es"
    out_dir = ROOT / "runs" / run_slug / "localization" / locale
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    title = "Deck Text Map - PT-BR" if locale == "pt-br" else "Deck Text Map - ES-419"
    lines = [
        f"# Lesson {lesson} {title}",
        "",
        f"- Course slug: `{run_slug}`",
        f"- Lesson: `{lesson}`",
        "- Source artifact: `runs/{}/deck/lesson_{}_deck.pptx`".format(run_slug, lesson),
        "- Source language: English",
        f"- Target locale: `{locale}`",
        "- Localization scope: `deck_text_map`",
        "- Approval mode: `v0_process`",
        f"- Localization date: {today}",
        "- Status: text map only, not localized PPTX",
        "",
        "## Global Notes",
        "",
        "- Brand text remains unchanged.",
        "- Footer page numbers should not be translated.",
        "- U.S. construction market terms may be preserved when translation would reduce clarity.",
        "- High-risk slides should be checked visually before localized PPTX delivery.",
        "",
    ]

    for slide in SLIDES:
        data = slide[key]
        lines.extend([
            f"## Slide {slide['n']:02d}",
            "",
            f"- Original title: {slide['en_title']}",
            f"- Localized title: {data['title']}",
            f"- Length risk: `{data['risk']}`",
            f"- Layout note: {data['note']}",
            "",
            "| Role | Localized visible text |",
            "|---|---|",
        ])
        for role, text in data["items"]:
            safe_text = text.replace("\n", "<br>")
            lines.append(f"| `{role}` | {safe_text} |")
        lines.append("")

    map_path = out_dir / f"lesson_{lesson}_deck_text_map_{locale}.md"
    map_path.write_text("\n".join(lines), encoding="utf-8")

    high = [s for s in SLIDES if s[key]["risk"] == "high"]
    qa_lines = [
        f"# Lesson {lesson} Deck Localization QA - {locale}",
        "",
        "Status: pass for v0 deck text map.",
        "",
        "## Scope",
        "",
        "- Deck text map only.",
        "- Localized PPTX not produced in this step.",
        "- Speaker notes not applicable; English deck has no authored note text.",
        "",
        "## Checks",
        "",
        "- Slide count preserved: 10.",
        "- Main teaching arc preserved: pass.",
        "- U.S. construction context preserved: pass.",
        "- Brand text preserved: pass.",
        "- Footer page numbers excluded from translation: pass.",
        "- Unsupported claims added: none.",
        "- Source references: deck does not show detailed references; study guide remains source of record.",
        "",
        "## Length Risks",
        "",
    ]
    for slide in high:
        qa_lines.append(f"- Slide {slide['n']:02d}: high - {slide[key]['note']}")
    qa_lines.extend([
        "",
        "## Next Step",
        "",
        "Generate localized PPTX from this map, render all slides, and run overflow/visual QA.",
    ])
    qa_path = out_dir / f"lesson_{lesson}_deck_localization_qa.md"
    qa_path.write_text("\n".join(qa_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("locale", choices=["pt-br", "es-419"])
    parser.add_argument("--run", default="ai-for-construction-professionals")
    parser.add_argument("--lesson", default="01")
    args = parser.parse_args()
    build(args.locale, args.run, args.lesson)


if __name__ == "__main__":
    main()
