$ErrorActionPreference = "Stop"

$mosq = Join-Path $env:ProgramFiles "mosquitto\mosquitto_pub.exe"
if (-not (Test-Path $mosq)) {
    throw "mosquitto_pub not found at $mosq"
}

$hostName = "homeassistant.local"
$port = 1883
$user = "mqtt"
$pass = "canon6dd"

$oldIds = @(
    "0d3c1f55_bb88_4ef7_a3e9_ef93ebcc8db1",
    "8fc9337d_99d4_4b05_9b5a_041bb21477f8"
)

foreach ($id in $oldIds) {
    & $mosq -h $hostName -p $port -u $user -P $pass -r -t "homeassistant/switch/snoozefest_alarm_${id}/config" -n
    & $mosq -h $hostName -p $port -u $user -P $pass -r -t "homeassistant/button/snoozefest_alarm_${id}_remove/config" -n
    & $mosq -h $hostName -p $port -u $user -P $pass -r -t "homeassistant/button/snoozefest_alarm_${id}_snooze/config" -n
    & $mosq -h $hostName -p $port -u $user -P $pass -r -t "homeassistant/button/snoozefest_alarm_${id}_dismiss/config" -n
    & $mosq -h $hostName -p $port -u $user -P $pass -r -t "homeassistant/sensor/snoozefest_alarm_${id}_status/config" -n
}

# Ask snoozefest to republish current state
& $mosq -h $hostName -p $port -u $user -P $pass -t "snoozefest/cmd/state/request" -m "{}"

Write-Host "Done. Old discovery entities cleared and state republish requested." -ForegroundColor Green
