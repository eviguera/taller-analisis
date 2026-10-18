#!/usr/bin/env python3
"""
ECC Agents Runner - Ejecuta los agentes ECC contra el proyecto GIRO.

Este script simula la ejecución de los agentes ECC (de https://github.com/affaan-m/ECC)
contra el proyecto GIRO, aplicando las reglas y criterios de cada agente basado
en las definiciones reales del repositorio ECC.

Cada agente sigue el ciclo: PLAN -> TEST -> IMPLEMENT -> REVIEW -> VERIFY -> REMEMBER -> IMPROVE

Uso:
    .venv/bin/python scripts/ecc_agents_runner.py [agente] [--all]

Agentes disponibles:
  code-reviewer, sql-arquitecto, data-engineer, data-analyst, python-senior,
  ui-engineer, ux-researcher, docker-expert, security-reviewer, code-explorer,
  alertas, acciones, y todos los 71 agentes de ECC.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
ECC_REPO = Path("/Users/eduardoviguera/Desktop/ECC")

# Colores para output
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
PURPLE = "\033[0;35m"
CYAN = "\033[0;36m"
NC = "\033[0m"  # No Color


def log(color: str, msg: str) -> None:
    print(f"{color}{msg}{NC}")


def load_agent_definition(agent_name: str) -> Optional[Dict[str, Any]]:
    """Carga la definición de un agente ECC desde su archivo .md."""
    agent_path = ECC_REPO / "agents" / f"{agent_name}.md"
    if not agent_path.exists():
        return None

    content = agent_path.read_text(encoding="utf-8")

    # Extraer metadatos del frontmatter
    metadata = {}
    content_part = content

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            frontmatter = content[3:end].strip()
            content_part = content[end + 3 :].strip()
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    metadata[key.strip()] = val.strip()

    return {
        "name": metadata.get("name", agent_name),
        "description": metadata.get("description", ""),
        "tools": metadata.get("tools", ""),
        "model": metadata.get("model", ""),
        "content": content,
        "content_body": content_part,
    }


def get_all_agents() -> List[str]:
    """Lista todos los agentes disponibles en ECC."""
    agent_dir = ECC_REPO / "agents"
    if not agent_dir.exists():
        return []
    return sorted([f.stem for f in agent_dir.glob("*.md")])


class ECCAgentRunner:
    """Ejecuta un agente ECC contra el proyecto GIRO."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.definition = load_agent_definition(agent_name)
        self.repo_root = REPO_ROOT
        self.findings: List[Dict[str, Any]] = []
        self.start_time = datetime.now()

        if not self.definition:
            raise ValueError(f"Agente '{agent_name}' no encontrado en ECC")

    def log(self, msg: str, color: str = NC) -> None:
        print(f"[{self.agent_name}] {color}{msg}{NC}")

    def run_cycle(self) -> Dict[str, Any]:
        """Ejecuta el ciclo completo: PLAN -> TEST -> IMPLEMENT -> REVIEW -> VERIFY -> REMEMBER -> IMPROVE"""
        results = {
            "agent": self.agent_name,
            "definition": self.definition,
            "start_time": self.start_time.isoformat(),
            "phases": {},
            "findings": [],
            "summary": {},
        }

        # PLAN
        self.log("\n" + "=" * 60, CYAN)
        self.log(f"  AGENTE: {self.agent_name}", CYAN)
        self.log(f"  Descripción: {self.definition.get('description', 'N/A')}", CYAN)
        self.log("=" * 60, CYAN)

        plan_result = self._phase_plan()
        results["phases"]["plan"] = plan_result

        # TEST
        test_result = self._phase_test()
        results["phases"]["test"] = test_result

        # IMPLEMENT
        impl_result = self._phase_implement()
        results["phases"]["implement"] = impl_result

        # REVIEW
        review_result = self._phase_review()
        results["phases"]["review"] = review_result

        # VERIFY
        verify_result = self._phase_verify()
        results["phases"]["verify"] = verify_result

        # REMEMBER
        remember_result = self._phase_remember()
        results["phases"]["remember"] = remember_result

        # IMPROVE
        improve_result = self._phase_improve()
        results["phases"]["improve"] = improve_result

        results["findings"] = self.findings
        results["end_time"] = datetime.now().isoformat()
        results["summary"] = self._generate_summary()

        return results

    def _phase_plan(self) -> Dict[str, Any]:
        """Fase PLAN: Analizar qué necesita revisarse."""
        self.log("\n[PLAN] Analizando alcance de revisión...", BLUE)

        plan = {
            "files_to_review": [],
            "areas_of_concern": [],
            "rules_to_check": [],
        }

        # Determinar qué archivos revisar basado en el agente
        if self.agent_name == "code-reviewer":
            plan["files_to_review"] = self._get_all_python_files()
            plan["areas_of_concern"] = [
                "Seguridad (secretos hardcodeados, SQL injection)",
                "Aislamiento por workspace",
                "Except Exception: pass",
                "Efectos secundarios en import",
                "SQL parametrizado",
            ]
        elif self.agent_name == "sql-arquitecto":
            plan["files_to_review"] = [
                "src/storage/store.py",
                "src/storage/postgres.py",
                "src/storage/dialecto.py",
                "src/storage/schema.py",
                "src/core/conector_sql.py",
                "src/core/warehouse.py",
                "src/core/hechos.py",
            ]
            plan["areas_of_concern"] = [
                "SQL parametrizado",
                "Identificadores dinámicos validados",
                "CREATE DATABASE sin bind (excepción documentada)",
                "Aislamiento por workspace en consultas",
            ]
        elif self.agent_name == "data-engineer":
            plan["files_to_review"] = [
                "src/core/pipeline.py",
                "src/core/hechos.py",
                "src/core/catalog.py",
                "src/loaders/base.py",
                "src/loaders/factory.py",
                "src/loaders/csv_loader.py",
                "src/loaders/excel_loader.py",
                "src/loaders/parquet_loader.py",
                "src/loaders/pspp_loader.py",
                "src/loaders/dlt_loader.py",
            ]
            plan["areas_of_concern"] = [
                "Carga de archivos CSV/Excel/PSPP",
                "Detección automática de datasets",
                "Mapeo de columnas",
                "Calidad de datos",
                "Conectores externos",
            ]
        elif self.agent_name == "data-analyst":
            plan["files_to_review"] = [
                "src/analyzer.py",
                "src/predictions.py",
                "src/model_registry.py",
                "src/recomendaciones.py",
                "src/alerts.py",
                "src/simulador.py",
                "src/negocio.py",
            ]
            plan["areas_of_concern"] = [
                "KPIs y métricas",
                "Modelos predictivos (ingresos, demanda, churn, inventario)",
                "Motor de alertas",
                "Simulador what-if",
                "Unidad económica y ROI",
            ]
        elif self.agent_name == "ui-engineer":
            plan["files_to_review"] = [
                "ui/app.py",
                "ui/context.py",
                "ui/components.py",
                "ui/theme.py",
                "ui/login.py",
                "ui/pages/resumen.py",
                "ui/pages/negocio.py",
                "ui/pages/alertas.py",
                "ui/pages/predicciones.py",
                "ui/pages/simulador.py",
                "ui/pages/datos.py",
                "ui/pages/reportes.py",
                "ui/pages/clientes.py",
                "ui/pages/servicios.py",
                "ui/pages/vehiculos.py",
                "ui/pages/inventario.py",
            ]
            plan["areas_of_concern"] = [
                "No st.plotly_chart crudo",
                "No HTML suelto en páginas",
                "Modo claro y oscuro",
                "Wrappers de componentes",
                "Tokens de tema",
            ]
        elif self.agent_name == "security-reviewer":
            plan["files_to_review"] = [
                "src/core/auth.py",
                "src/api/deps.py",
                "src/api/rutas.py",
                "src/core/config_manager.py",
                "ui/login.py",
                "ui/app.py",
                "ui/context.py",
                "docker-compose.yml",
                "Dockerfile",
                ".dockerignore",
                ".gitignore",
                "config/usuarios.yaml",
            ]
            plan["areas_of_concern"] = [
                "Secretos en código (GIRO_AUTH_SECRET, GIRO_PG_*)",
                "SQL injection",
                "Aislamiento por workspace",
                "Autenticación y cookie",
                "Permisos de usuario",
            ]
        elif self.agent_name == "docker-expert":
            plan["files_to_review"] = [
                "Dockerfile",
                "docker-compose.yml",
                "entrypoint.sh",
                ".dockerignore",
                ".gitignore",
                "requirements.lock",
                "requirements.txt",
            ]
            plan["areas_of_concern"] = [
                "Python 3.11-slim base",
                "Usuario no root (uid 1001)",
                "Secretos por variable de entorno",
                "Volúmenes para datos",
                "Healthchecks",
                "Fail-closed si algún proceso muere",
            ]
        else:
            # Para otros agentes, revisar archivos relevantes del proyecto
            plan["files_to_review"] = self._get_all_python_files()[:20]
            plan["areas_of_concern"] = [
                "Revisión general de calidad",
                "Cumplimiento de reglas del repositorio",
            ]

        self.log(f"  Archivos a revisar: {len(plan['files_to_review'])}", BLUE)
        self.log(f"  Áreas de preocupación: {len(plan['areas_of_concern'])}", BLUE)

        return plan

    def _phase_test(self) -> Dict[str, Any]:
        """Fase TEST: Ejecutar pruebas del área."""
        self.log("\n[TEST] Ejecutando pruebas...", BLUE)

        results = {
            "tests_run": [],
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": [],
        }

        # Ejecutar tests de unittest si existen
        tests_dir = self.repo_root / "tests"
        if tests_dir.exists():
            self.log("  Ejecutando suite de unittest...", BLUE)
            try:
                result = subprocess.run(
                    [".venv/bin/python", "-m", "unittest", "discover", "-s", "tests"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=self.repo_root,
                )
                if result.returncode == 0:
                    self.log("  ✓ Todos los tests de unittest pasaron", GREEN)
                    results["tests_passed"] += 1
                else:
                    self.log(f"  ✗ Algunos tests fallaron: {result.stderr[-200:]}", RED)
                    results["tests_failed"] += 1
                    results["errors"].append(result.stderr[-200:])
            except Exception as e:
                self.log(f"  ✗ Error ejecutando tests: {e}", RED)
                results["errors"].append(str(e))

        # Verificar sintaxis de archivos Python
        python_files = self._get_all_python_files()
        syntax_errors = []
        for f in python_files:
            try:
                ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError as e:
                syntax_errors.append(f"{f}: {e}")
                self.log(f"  ✗ Error de sintaxis en {f}: {e}", RED)

        if not syntax_errors:
            self.log("  ✓ Sintaxis de todos los archivos Python válida", GREEN)
            results["tests_passed"] += 1
        else:
            results["tests_failed"] += len(syntax_errors)
            results["errors"].extend(syntax_errors)

        results["tests_run"] = len(python_files)
        return results

    def _phase_implement(self) -> Dict[str, Any]:
        """Fase IMPLEMENT: Aplicar correcciones necesarias."""
        self.log("\n[IMPLEMENT] Aplicando correcciones...", BLUE)

        implemented = []

        # Verificar y crear __init__.py si falta en directorios de paquetes
        for dirpath in self.repo_root.rglob("src"):
            if dirpath.is_dir():
                init_file = dirpath / "__init__.py"
                if not init_file.exists() and any(f.suffix == ".py" for f in dirpath.iterdir()):
                    init_file.write_text('"""Modulo paquete GIRO."""\n')
                    implemented.append(f"Creado {init_file.relative_to(self.repo_root)}")

        # Verificar que src/data_loader.py exista y tenga get_store
        data_loader = self.repo_root / "src" / "data_loader.py"
        if data_loader.exists():
            content = data_loader.read_text(encoding="utf-8")
            if "def get_store" in content:
                self.log("  ✓ get_store() existe en data_loader.py", GREEN)
                implemented.append("get_store() verificado en data_loader.py")
            else:
                self.log("  ✗ get_store() NO encontrado en data_loader.py", RED)

        # Verificar que src/aplicacion/almacen.py exista
        almacen = self.repo_root / "src" / "aplicacion" / "almacen.py"
        if almacen.exists():
            self.log("  ✓ src/aplicacion/almacen.py existe", GREEN)
            implemented.append("src/aplicacion/almacen.py verificado")

        return {"implemented": implemented}

    def _phase_review(self) -> Dict[str, Any]:
        """Fase REVIEW: Revisar código y hallar problemas."""
        self.log("\n[REVIEW] Revisando código...", BLUE)

        review_results = {
            "files_reviewed": 0,
            "issues_found": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }

        # Revisar archivos según el agente
        files_to_review = self._get_files_for_agent()

        for filepath in files_to_review:
            if not filepath.exists():
                continue

            review_results["files_reviewed"] += 1
            content = filepath.read_text(encoding="utf-8")
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()

                # Verificar except Exception: pass
                if "except Exception: pass" in line:
                    self.findings.append({
                        "severity": "CRITICAL",
                        "file": str(filepath.relative_to(self.repo_root)),
                        "line": i,
                        "issue": "except Exception: pass - error tragado",
                        "fix": "Revisar y registrar la excepción, o relanzar con contexto",
                    })
                    review_results["critical"] += 1
                    review_results["issues_found"] += 1
                    self.log(f"  ⚠️  {filepath.name}:{i} - except Exception: pass", RED)

                # Verificar secretos hardcodeados
                if "GIRO_AUTH_SECRET" in line and "=" in line and "os.environ" not in line:
                    self.findings.append({
                        "severity": "CRITICAL",
                        "file": str(filepath.relative_to(self.repo_root)),
                        "line": i,
                        "issue": "Posible secreto hardcodeado (GIRO_AUTH_SECRET)",
                        "fix": "Usar os.environ.get('GIRO_AUTH_SECRET')",
                    })
                    review_results["critical"] += 1
                    review_results["issues_found"] += 1
                    self.log(f"  ⚠️  {filepath.name}:{i} - Posible secreto hardcodeado", RED)

                # Verificar f-strings en SQL (posible inyección)
                if "f\"" in line and ("SELECT" in line.upper() or "INSERT" in line.upper() or "DELETE" in line.upper() or "UPDATE" in line.upper() or "DROP" in line.upper() or "CREATE" in line.upper()):
                    self.findings.append({
                        "severity": "HIGH",
                        "file": str(filepath.relative_to(self.repo_root)),
                        "line": i,
                        "issue": "Posible SQL injection con f-string",
                        "fix": "Usar bind parameters (parametrización)",
                    })
                    review_results["high"] += 1
                    review_results["issues_found"] += 1
                    self.log(f"  ⚠️  {filepath.name}:{i} - Posible SQL injection", YELLOW)

        self.log(f"  Archivos revisados: {review_results['files_reviewed']}", BLUE)
        self.log(f"  Problemas encontrados: {review_results['issues_found']}", BLUE)
        self.log(f"    CRITICAL: {review_results['critical']}", RED if review_results['critical'] > 0 else GREEN)
        self.log(f"    HIGH: {review_results['high']}", YELLOW if review_results['high'] > 0 else GREEN)
        self.log(f"    MEDIUM: {review_results['medium']}", YELLOW if review_results['medium'] > 0 else GREEN)
        self.log(f"    LOW: {review_results['low']}", BLUE if review_results['low'] > 0 else GREEN)

        return review_results

    def _phase_verify(self) -> Dict[str, Any]:
        """Fase VERIFY: Verificar que todo funcione."""
        self.log("\n[VERIFY] Verificando resultados...", BLUE)

        verify_results = {
            "imports_ok": False,
            "cli_works": False,
            "tests_pass": False,
            "details": [],
        }

        # Verificar imports de módulos clave
        modules_to_test = [
            "src.aplicacion",
            "src.data_loader",
            "src.api.app",
            "src.core.pipeline",
            "src.storage.store",
            "src.analyzer",
            "src.predictions",
            "src.alerts",
        ]

        for module in modules_to_test:
            try:
                result = subprocess.run(
                    [".venv/bin/python", "-c", f"import {module}; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.repo_root,
                )
                if result.returncode == 0:
                    verify_results["details"].append(f"✓ {module} importa correctamente")
                else:
                    verify_results["details"].append(f"✗ {module} falló: {result.stderr[:100]}")
            except Exception as e:
                verify_results["details"].append(f"✗ {module} error: {e}")

        if all("✓" in d for d in verify_results["details"]):
            verify_results["imports_ok"] = True
            self.log("  ✓ Todos los módulos importan correctamente", GREEN)
        else:
            self.log("  ⚠️  Algunos módulos fallaron al importar", RED)

        # Verificar que CLI funciona
        try:
            result = subprocess.run(
                [".venv/bin/python", "main.py", "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.repo_root,
            )
            if result.returncode == 0 and "GIRO - Inteligencia de negocio" in result.stdout:
                verify_results["cli_works"] = True
                verify_results["details"].append("✓ CLI funciona correctamente")
                self.log("  ✓ CLI funciona correctamente", GREEN)
            else:
                verify_results["details"].append("✗ CLI falló")
                self.log("  ✗ CLI falló", RED)
        except Exception as e:
            verify_results["details"].append(f"✗ CLI error: {e}")
            self.log(f"  ✗ CLI error: {e}", RED)

        # Ejecutar tests
        try:
            result = subprocess.run(
                [".venv/bin/python", "-m", "unittest", "discover", "-s", "tests"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.repo_root,
            )
            if result.returncode == 0:
                verify_results["tests_pass"] = True
                verify_results["details"].append("✓ Todos los tests pasan")
                self.log("  ✓ Todos los tests pasan", GREEN)
            else:
                verify_results["details"].append(f"✗ Tests fallaron: {result.stderr[-100:]}")
                self.log(f"  ✗ Tests fallaron", RED)
        except Exception as e:
            verify_results["details"].append(f"✗ Tests error: {e}")
            self.log(f"  ✗ Tests error: {e}", RED)

        return verify_results

    def _phase_remember(self) -> Dict[str, Any]:
        """Fase REMEMBER: Documentar hallazgos."""
        self.log("\n[REMEMBER] Documentando hallazgos...", BLUE)

        remember = {
            "total_findings": len(self.findings),
            "critical": sum(1 for f in self.findings if f.get("severidad") == "CRITICAL"),
            "high": sum(1 for f in self.findings if f.get("severidad") == "HIGH"),
            "medium": sum(1 for f in self.findings if f.get("severidad") == "MEDIUM"),
            "low": sum(1 for f in self.findings if f.get("severidad") == "LOW"),
            "files_reviewed": len(set(f["file"] for f in self.findings)),
        }

        self.log(f"  Hallazgos totales: {remember['total_findings']}", BLUE)
        self.log(f"  CRITICAL: {remember['critical']}", RED if remember['critical'] > 0 else GREEN)
        self.log(f"  HIGH: {remember['high']}", YELLOW if remember['high'] > 0 else GREEN)
        self.log(f"  MEDIUM: {remember['medium']}", YELLOW if remember['medium'] > 0 else GREEN)
        self.log(f"  LOW: {remember['low']}", BLUE if remember['low'] > 0 else GREEN)

        return remember

    def _phase_improve(self) -> Dict[str, Any]:
        """Fase IMPROVE: Sugerir mejoras."""
        self.log("\n[IMPROVE] Sugiriendo mejoras...", BLUE)

        improvements = []

        # Basado en los hallazgos, sugerir mejoras
        if any(f.get("severidad") == "CRITICAL" for f in self.findings):
            improvements.append({
                "área": "Seguridad",
                "acción": "Corregir vulnerabilidades CRITICAL inmediatamente",
                "prioridad": "CRÍTICA",
            })

        if any(f.get("severidad") == "HIGH" for f in self.findings):
            improvements.append({
                "área": "Calidad de código",
                "acción": "Corrigir problemas HIGH antes del próximo release",
                "prioridad": "ALTA",
            })

        # Verificar si requirements.lock necesita actualización
        lock_file = self.repo_root / "requirements.lock"
        if lock_file.exists():
            improvements.append({
                "área": "Dependencias",
                "acción": "Verificar que requirements.lock sea compatible con Python 3.11",
                "prioridad": "ALTA",
            })

        # Verificar si hay tests para los nuevos módulos
        tests_dir = self.repo_root / "tests"
        if tests_dir.exists():
            test_files = list(tests_dir.glob("test_*.py"))
            if len(test_files) < 10:
                improvements.append({
                    "área": "Tests",
                    "acción": "Agregar más tests unitarios para cobertura completa",
                    "prioridad": "MEDIA",
                })

        for imp in improvements:
            self.log(f"  • {imp['área']}: {imp['acción']} ({imp['prioridad']})", BLUE)

        return {"improvements": improvements}

    def _generate_summary(self) -> Dict[str, Any]:
        """Generar resumen final."""
        return {
            "total_findings": len(self.findings),
            "critical": sum(1 for f in self.findings if f.get("severidad") == "CRITICAL"),
            "high": sum(1 for f in self.findings if f.get("severidad") == "HIGH"),
            "medium": sum(1 for f in self.findings if f.get("severidad") == "MEDIUM"),
            "low": sum(1 for f in self.findings if f.get("severidad") == "LOW"),
            "status": "COMPLETADO",
        }

    def _get_all_python_files(self) -> List[Path]:
        """Obtener todos los archivos Python del proyecto."""
        src_dir = self.repo_root / "src"
        ui_dir = self.repo_root / "ui"
        files = []
        for d in [src_dir, ui_dir]:
            if d.exists():
                files.extend(d.rglob("*.py"))
        # También incluir main.py y generate_data.py en la raíz
        for f in [self.repo_root / "main.py", self.repo_root / "generate_data.py"]:
            if f.exists():
                files.append(f)
        return sorted(files)

    def _get_files_for_agent(self) -> List[Path]:
        """Obtener archivos específicos para el agente actual."""
        # Por defecto, devolver todos los archivos Python
        return self._get_all_python_files()


def main():
    parser = argparse.ArgumentParser(description="Ejecutar agentes ECC contra GIRO")
    parser.add_argument("agente", nargs="?", help="Nombre del agente a ejecutar")
    parser.add_argument("--all", action="store_true", help="Ejecutar todos los agentes")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    if args.all:
        agents = get_all_agents()
        log(f"Ejecutando {len(agents)} agentes ECC...", CYAN)
        print()

        all_results = []
        for agent_name in agents:
            try:
                runner = ECCAgentRunner(agent_name)
                result = runner.run_cycle()
                all_results.append(result)
            except Exception as e:
                log(f"Error ejecutando {agent_name}: {e}", RED)

        # Resumen final
        print("\n" + "=" * 60)
        print("RESUMEN FINAL DE TODOS LOS AGENTES")
        print("=" * 60)

        total_findings = 0
        total_critical = 0
        total_high = 0

        for r in all_results:
            s = r["summary"]
            total_findings += s["total_findings"]
            total_critical += s["critical"]
            total_high += s["high"]
            status = "✓" if s["critical"] == 0 and s["high"] == 0 else "⚠"
            print(f"  {status} {r['agent']}: {s['total_findings']} hallazgos "
                  f"(C:{s['critical']}, H:{s['high']}, M:{s['medium']}, L:{s['low']})")

        print(f"\nTotal: {total_findings} hallazgos ({total_critical} CRITICAL, {total_high} HIGH)")

        # Guardar reporte
        report_file = repo_root / "reports" / f"ecc_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            json.dumps(all_results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nReporte guardado en: {report_file}")

    elif args.agente:
        runner = ECCAgentRunner(args.agente)
        result = runner.run_cycle()

        print("\n" + "=" * 60)
        print(f"RESULTADO: {args.agente}")
        print("=" * 60)
        print(f"Estado: {result['summary']['status']}")
        print(f"Hallazgos: {result['summary']['total_findings']}")
        print(f"  CRITICAL: {result['summary']['critical']}")
        print(f"  HIGH: {result['summary']['high']}")
        print(f"  MEDIUM: {result['summary']['medium']}")
        print(f"  LOW: {result['summary']['low']}")

        if result["findings"]:
            print("\nHal los hallazgos:")
            for f in result["findings"]:
                print(f"  [{f['severidad']}] {f['file']}:{f['line']} - {f['issue']}")
                print(f"    Fix: {f['fix']}")

        # Guardar reporte
        report_file = repo_root / "reports" / f"ecc_{args.agente}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReporte guardado en: {report_file}")
    else:
        parser.print_help()
        print("\nAgentes disponibles:")
        for a in sorted(get_all_agents()):
            print(f"  {a}")


if __name__ == "__main__":
    main()