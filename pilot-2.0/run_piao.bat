@echo off
REM ============================================================
REM  Piao 原版 simulate_debiased.py 启动脚本
 REM  CWD 必须是 pilot-2.0/（双击此文件会自动设为脚本所在目录）
REM ============================================================
cd /d "%~dp0"

REM === 议题配置：Politics（共和 vs 民主）。换议题只改这 13 行 + abb ===
set "ENV_STR=Sociopolitical"
set "TOPIC=Politics"
set "S_M2=strongly support the Republican party"
set "S_M1=support the Republican party"
set "S_0=don't have a tendency"
set "S_P1=support the Democratic party"
set "S_P2=Strongly support the Democratic party"
set "S_M2_E=the Republic party is absolutely better than the Democratic party in every aspect."
set "S_M1_E=the Republican party and the Democratic party both have ups and downs, but the Republican party have a slight edge."
set "S_0_E=doesn't lean towards or favor either the Democratic or Republican party."
set "S_P1_E=the Democratic party and the Republican party both have ups and downs, but the Democratic party have a slight edge."
set "S_P2_E=the Democratic party is absolutely better than the Republican party in every aspect."
set "SIDE_B=Support the Democratic party"
set "SIDE_S=Support the Republican party"
set "SIDE_E=Maintain neutrality"

REM === 运行配置：smoke 用 num_epoch=5，正式跑改 50 ===
set "DATASOURCE=data/WS_80"
set "NUM_EPOCH=5"
set "SIDE_INIT=0.1,0.2,0.4,0.2,0.1"
set "ABB=Politics"
set "START_EP=0"

echo ============================================================
echo   Topic     : %TOPIC%
echo   Data      : %DATASOURCE%
echo   Epoch     : %NUM_EPOCH%
echo   Init dist : %SIDE_INIT%
echo ============================================================

python src/simulate_debiased.py ^
  "%ENV_STR%" "%TOPIC%" ^
  "%S_M2%" "%S_M1%" "%S_0%" "%S_P1%" "%S_P2%" ^
  "%S_M2_E%" "%S_M1_E%" "%S_0_E%" "%S_P1_E%" "%S_P2_E%" ^
  "%SIDE_B%" "%SIDE_S%" "%SIDE_E%" ^
  "%DATASOURCE%" "%NUM_EPOCH%" "%SIDE_INIT%" "%ABB%" "%START_EP%"

echo.
echo ============================================================
echo   Exit code: %ERRORLEVEL%
echo   Output   : output_pol/e%NUM_EPOCH%_prob%SIDE_INIT%_%DATASOURCE%_%ABB%/
echo ============================================================
pause