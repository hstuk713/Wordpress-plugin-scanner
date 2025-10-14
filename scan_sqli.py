#!/usr/bin/env python3
"""
Per-file semgrep scanner for plugin directory (recursive).

동작:
- plugin_dir 하위의 모든 .php 파일을 재귀적으로 찾음
- 각 파일마다 semgrep을 개별적으로 실행하여 임시 JSON 출력 생성
- 임시 JSON들을 병합하여 최종 output_json에 저장
- 파일별 검사 결과(성공/실패/매칭수) 요약 출력
"""
import shutil
import subprocess
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
import time

def gather_php_files_recursive(plugin_dir: str) -> List[str]:
    p = Path(plugin_dir)
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"plugin 디렉터리({plugin_dir})가 존재하지 않거나 디렉터리가 아님")
    php_files = [str(fp) for fp in p.rglob("*.php")]
    php_files.sort()
    return php_files

def run_semgrep_for_file(
    semgrep_path: str,
    config: str,
    file_path: str,
    tmp_output: str,
    extra_args: List[str] = None,
    timeout: int = 120
) -> Dict[str, Any]:
    if extra_args is None:
        extra_args = ["--no-git-ignore", "--quiet"]
    # Command: semgrep --config config --json --output tmp_output [extra_args] file_path
    cmd = [semgrep_path, "--config", config, "--json", "--output", tmp_output] + extra_args + [file_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return {"returncode": -1, "stdout": e.stdout or "", "stderr": f"TimeoutExpired: {e}", "output_exists": Path(tmp_output).exists()}
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "output_exists": Path(tmp_output).exists()}

def merge_semgrep_jsons(json_paths: List[str]) -> Dict[str, Any]:
    merged = {"results": []}
    for jp in json_paths:
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
                merged["results"].extend(data["results"])
            else:
                if isinstance(data, list):
                    merged["results"].extend(data)
        except Exception as e:
            print(f"[WARN] JSON 병합 중 오류({jp}): {e}", file=sys.stderr)
    return merged

def summarize_results(merged: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in merged.get("results", []):
        path = None
        if isinstance(r, dict):
            if "path" in r and isinstance(r["path"], str):
                path = r["path"]
            else:
                extra = r.get("extra")
                if isinstance(extra, dict):
                    if "path" in extra and isinstance(extra["path"], str):
                        path = extra["path"]
                    elif "filename" in extra and isinstance(extra["filename"], str):
                        path = extra["filename"]
                    elif "metadata" in extra and isinstance(extra["metadata"], dict):
                        md = extra["metadata"]
                        if "filename" in md:
                            path = md["filename"]
        if path is None:
            path = "<unknown>"
        counts[path] = counts.get(path, 0) + 1
    return counts

def scan_plugin_dir_per_file(
    plugin_dir: str = "plugin",
    config: str = "php_sqli_rules.yaml",
    output_json: str = "sqli_results.json",
    timeout_per_file: int = 120,
    extra_args: List[str] = None
) -> int:
    semgrep_path = shutil.which("semgrep")
    if semgrep_path is None:
        print("[ERROR] semgrep이 PATH에 없습니다. 설치하거나 PATH를 확인하세요.", file=sys.stderr)
        return 2

    try:
        php_files = gather_php_files_recursive(plugin_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3

    if not php_files:
        print("[INFO] PHP 파일을 찾지 못했습니다. 종료합니다.")
        return 0

    print(f"[INFO] 총 PHP 파일 수: {len(php_files)} (하위 디렉터리 포함, 파일별 분석)")

    tmp_jsons: List[str] = []
    results_per_file: Dict[str, Dict[str, Any]] = {}
    start_time = time.time()

    for idx, php_file in enumerate(php_files, start=1):
        safe_idx = idx
        tmp_output = f".semgrep_tmp_file_{safe_idx}.json"
        print(f"[{idx}/{len(php_files)}] 검사 중: {php_file} -> {tmp_output}")
        res = run_semgrep_for_file(
            semgrep_path=semgrep_path,
            config=config,
            file_path=php_file,
            tmp_output=tmp_output,
            extra_args=extra_args,
            timeout=timeout_per_file
        )
        results_per_file[php_file] = res
        if res.get("output_exists"):
            tmp_jsons.append(tmp_output)
            # optionally: quickly read the tmp json to count matches for progress
            try:
                with open(tmp_output, "r", encoding="utf-8") as f:
                    data = json.load(f)
                match_count = 0
                if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
                    match_count = len(data["results"])
                elif isinstance(data, list):
                    match_count = len(data)
                print(f"  -> 완료: 매칭 {match_count}개")
            except Exception:
                print("  -> 완료: 결과는 있으나 parsing 실패", file=sys.stderr)
        else:
            print(f"  -> 경고: semgrep 결과 파일 미생성 (returncode={res.get('returncode')})", file=sys.stderr)
            if res.get("stderr"):
                print(f"     stderr: {res.get('stderr')[:800]}", file=sys.stderr)

    elapsed = time.time() - start_time
    print(f"[INFO] 파일별 검사 완료. 소요시간: {elapsed:.1f}s. JSON 병합 중...")

    merged = merge_semgrep_jsons(tmp_jsons)

    try:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 최종 결과 저장: {output_json}")
    except Exception as e:
        print(f"[ERROR] 결과 저장 실패: {e}", file=sys.stderr)
        return 4

    counts = summarize_results(merged)
    total_matches = sum(counts.values())
    print(f"[SUMMARY] 전체 매칭 수: {total_matches}")
    if total_matches == 0:
        print("[SUMMARY] 취약점(매칭) 없음.")
    else:
        sorted_items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        print("[SUMMARY] 파일별 상위 매칭 (최대 20):")
        for path, cnt in sorted_items[:20]:
            print(f"  {cnt:4d}  {path}")

    # 임시 파일 정리
    for t in tmp_jsons:
        try:
            os.remove(t)
        except Exception:
            pass

    # 반환 코드: 하나라도 non-zero이면 1(주의: semgrep는 매칭 있어도 0 반환 가능)
    any_nonzero = any(res.get("returncode", 0) != 0 for res in results_per_file.values())
    if any_nonzero:
        print("[WARN] semgrep 실행 중 일부 파일에서 비정상 종료가 발생했음. stderr 확인 필요.", file=sys.stderr)
        # 상세 stderr 출력 요약(원하면 더 자세히 표시)
        for fpath, r in results_per_file.items():
            if r.get("returncode", 0) != 0:
                print(f"  - {fpath}: returncode={r.get('returncode')}, stderr={ (r.get('stderr') or '')[:300].replace(chr(10),' ')}")
        return 1

    return 0

if __name__ == "__main__":
    # 기본 설정 — 필요하면 해당 값들 수정해서 사용
    plugin_dir = "plugin"                     # plugin 폴더 경로
    config = "php_sqli_rules.yaml"            # 규칙 파일 경로
    output_json = "sqli_results.json"         # 최종 병합 결과 파일
    timeout_per_file = 120                    # 파일 당 timeout (초)
    extra_args = ["--no-git-ignore", "--quiet"]  # semgrep에 추가 전달할 args

    exit_code = scan_plugin_dir_per_file(
        plugin_dir=plugin_dir,
        config=config,
        output_json=output_json,
        timeout_per_file=timeout_per_file,
        extra_args=extra_args
    )
    if exit_code == 0:
        print("[EXIT] 정상 완료")
    else:
        print(f"[EXIT] 비정상 종료 코드: {exit_code}", file=sys.stderr)
    sys.exit(exit_code)