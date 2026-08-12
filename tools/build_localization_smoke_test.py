#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


PT_BR = {
    "course": "IA para Profissionais da Construção",
    "title": "IA na Construção: do Hype à Realidade",
    "subtitle": "Entenda o que a IA é, o que ela não é, e como avaliar seu valor real na construção.",
    "objectives": [
        "Definir IA em termos práticos para a construção.",
        "Diferenciar IA, automação, machine learning, IA generativa e análise preditiva em nível introdutório.",
        "Identificar categorias comuns de uso de IA na construção.",
        "Explicar por que resultados de IA exigem revisão humana em trabalhos técnicos de construção.",
        "Usar um filtro simples para separar valor real de marketing exagerado.",
    ],
    "sample_heading": "Introdução",
    "sample_body": (
        "A Inteligência Artificial já não é apenas uma manchete de tecnologia. "
        "Ela começa a aparecer em escritórios de construção, fluxos de estimativa, dashboards de segurança, "
        "coordenação BIM, documentação de projeto e ferramentas de dados de campo. "
        "Isso não significa que a IA seja mágica. Também não significa que todo produto chamado de "
        "\"AI-powered\" mereça confiança."
    ),
    "caption": (
        "A Lição 1 cria a camada de julgamento para todo o curso: antes de estudar IA em estimating, "
        "safety, BIM, acompanhamento de obra ou implementação, você precisa saber separar apoio útil "
        "de promessa sem evidência."
    ),
    "glossary": [
        ("Artificial Intelligence", "Sistemas computacionais que executam tarefas associadas à inteligência humana, como reconhecer padrões, classificar informações, gerar conteúdo ou apoiar decisões."),
        ("Confabulation", "Resultado de IA generativa que apresenta conteúdo falso ou incorreto com aparência confiante."),
        ("Predictive Analytics", "Uso de dados e modelos para estimar o que pode acontecer em seguida, como risco de cronograma, manutenção ou segurança."),
    ],
    "qa_tone": "PT-BR com você, informal, claro e profissional.",
    "qa_terms": "Termos do mercado dos EUA foram preservados quando a tradução poderia reduzir clareza, como BIM, estimating e safety.",
    "lesson_label": "LIÇÃO",
    "metadata_heading": "Metadados de localização",
    "objectives_heading": "Objetivos de aprendizagem",
    "caption_heading": "Amostra de legenda de figura",
    "glossary_heading": "Amostra de glossário",
    "term_header": "Termo",
    "definition_header": "Explicação localizada",
    "source_heading": "Amostra de preservação de fontes",
    "source_note": "Referências como `[S001]`, `[S002]` e `[S004]` devem continuar rastreáveis ao source ledger em inglês.",
    "deck_heading": "Prontidão para localização do deck",
    "deck_source_label": "Deck em inglês",
    "deck_not_localized": "Este smoke test ainda não localiza o PPTX.",
    "deck_text_map": "O texto dos slides deve ser localizado por meio de um mapa de texto do deck antes da renderização em PPTX.",
}


ES_419 = {
    "course": "IA para Profesionales de la Construcción",
    "title": "IA en la Construcción: de la Exageración a la Realidad",
    "subtitle": "Comprende qué es la IA, qué no es, y cómo evaluar su valor real en la construcción.",
    "objectives": [
        "Definir la IA en términos prácticos para la construcción.",
        "Distinguir IA, automatización, machine learning, IA generativa y análisis predictivo en un nivel introductorio.",
        "Identificar categorías comunes de uso de IA en la construcción.",
        "Explicar por qué los resultados de IA requieren revisión humana en trabajos técnicos de construcción.",
        "Usar un filtro simple para separar valor creíble de exageración comercial.",
    ],
    "sample_heading": "Introducción",
    "sample_body": (
        "La Inteligencia Artificial ya no es solo un titular tecnológico. "
        "Está empezando a aparecer en oficinas de construcción, flujos de estimación, tableros de seguridad, "
        "coordinación BIM, documentación de proyectos y herramientas de datos de campo. "
        "Eso no significa que la IA sea magia. Tampoco significa que todo producto etiquetado como "
        "\"AI-powered\" merezca confianza."
    ),
    "caption": (
        "La Lección 1 construye la capa de criterio para todo el curso: antes de estudiar IA en estimating, "
        "safety, BIM, seguimiento de obra o implementación, necesitas saber separar apoyo útil "
        "de promesas sin evidencia."
    ),
    "glossary": [
        ("Artificial Intelligence", "Sistemas informáticos que realizan tareas asociadas con la inteligencia humana, como reconocer patrones, clasificar información, generar contenido o apoyar decisiones."),
        ("Confabulation", "Resultado de IA generativa que presenta contenido falso o erróneo con apariencia confiada."),
        ("Predictive Analytics", "Uso de datos y modelos para estimar lo que puede ocurrir después, como riesgo de cronograma, mantenimiento o seguridad."),
    ],
    "qa_tone": "ES-419 neutral, claro, directo y profesional.",
    "qa_terms": "Se preservó el contexto del mercado de EE. UU.; términos como BIM, estimating y safety quedan como términos de referencia cuando evitan ambigüedad regional.",
    "lesson_label": "LECCIÓN",
    "metadata_heading": "Metadatos de localización",
    "objectives_heading": "Objetivos de aprendizaje",
    "caption_heading": "Muestra de leyenda de figura",
    "glossary_heading": "Muestra de glosario",
    "term_header": "Término",
    "definition_header": "Explicación localizada",
    "source_heading": "Muestra de preservación de fuentes",
    "source_note": "Referencias como `[S001]`, `[S002]` y `[S004]` deben seguir siendo trazables al source ledger en inglés.",
    "deck_heading": "Preparación para localización del deck",
    "deck_source_label": "Deck en inglés",
    "deck_not_localized": "Este smoke test todavía no localiza el PPTX.",
    "deck_text_map": "El texto de las diapositivas debe localizarse mediante un mapa de texto del deck antes de la renderización en PPTX.",
}


def build(locale: str, run_slug: str, lesson: str) -> None:
    data = {"pt-br": PT_BR, "es-419": ES_419}[locale]
    run_dir = ROOT / "runs" / run_slug
    out_dir = run_dir / "localization" / locale
    out_dir.mkdir(parents=True, exist_ok=True)

    source_artifact = f"runs/{run_slug}/docx_pdf/lesson_{lesson}_study_guide.pdf"
    deck_artifact = f"runs/{run_slug}/deck/lesson_{lesson}_deck.pptx"
    today = date.today().isoformat()

    md = [
        f"# {data['course']}",
        "",
        f"## {data['lesson_label']} {int(lesson)}",
        "",
        f"# {data['title']}",
        "",
        data["subtitle"],
        "",
        "---",
        "",
        f"## {data['metadata_heading']}",
        "",
        f"- Course slug: `{run_slug}`",
        f"- Lesson: `{lesson}`",
        f"- Source artifact: `{source_artifact}`",
        "- Source language: English",
        f"- Target locale: `{locale}`",
        "- Localization scope: `smoke_test`",
        "- Approval mode: `v0_process`",
        f"- Localization date: {today}",
        "- Status: smoke test, not full localized study guide",
        "",
        f"## {data['objectives_heading']}",
        "",
    ]
    md.extend([f"{i}. {text}" for i, text in enumerate(data["objectives"], 1)])
    md.extend([
        "",
        f"## {data['sample_heading']}",
        "",
        data["sample_body"],
        "",
        f"## {data['caption_heading']}",
        "",
        data["caption"],
        "",
        f"## {data['glossary_heading']}",
        "",
        f"| {data['term_header']} | {data['definition_header']} |",
        "|---|---|",
    ])
    md.extend([f"| {term} | {definition} |" for term, definition in data["glossary"]])
    md.extend([
        "",
        f"## {data['source_heading']}",
        "",
        data["source_note"],
        "",
        f"## {data['deck_heading']}",
        "",
        f"- {data['deck_source_label']}: `{deck_artifact}`",
        f"- {data['deck_not_localized']}",
        f"- {data['deck_text_map']}",
    ])

    (out_dir / f"lesson_{lesson}_study_guide_{locale}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    qa = [
        f"# Lesson {lesson} Localization QA - {locale}",
        "",
        "Status: pass for v0 smoke test.",
        "",
        "## Scope",
        "",
        "- Smoke test only.",
        "- Localized title, subtitle, learning objectives, one introduction sample, one figure caption sample, and glossary sample.",
        "- Full study guide localization not yet produced.",
        "- Deck PPTX localization not yet produced.",
        "",
        "## Checks",
        "",
        "- Meaning preserved: pass for sampled content.",
        "- U.S. construction market context preserved: pass.",
        f"- Tone: {data['qa_tone']}",
        f"- Terminology: {data['qa_terms']}",
        "- Units: no unit conversion needed in the sampled content.",
        "- References: source IDs preserved by policy; sample includes reference preservation note.",
        "- Visual captions: caption sample localized; future image text must be handled separately.",
        "- Unsupported claims: no new claims added.",
        "",
        "## Risks Before Full Localization",
        "",
        "- Full apostila translation needs terminology consistency checks across all sections.",
        "- Deck localization needs slide text length control because translated text may expand.",
        "- Any visual with embedded English text needs regeneration or translated caption/subtitle handling.",
    ]
    (out_dir / f"lesson_{lesson}_localization_qa.md").write_text("\n".join(qa) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("locale", choices=["pt-br", "es-419"])
    parser.add_argument("--run", default="ai-for-construction-professionals")
    parser.add_argument("--lesson", default="01")
    args = parser.parse_args()
    build(args.locale, args.run, args.lesson)


if __name__ == "__main__":
    main()
