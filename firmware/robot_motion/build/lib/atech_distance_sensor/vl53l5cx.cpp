/**
 * @file vl53l5cx.cpp
 * @brief VL53L5CX Multi-Resolution ToF Distance Sensor implementation for Athera
 *
 * A background FreeRTOS task polls the sensor and caches the distance grid at
 * the currently selected resolution. Public methods return cached values for
 * non-blocking access. The grid resolution can be changed at runtime via
 * setGridMode(); the reconfiguration is performed by the ranging task itself so
 * the sensor is only ever touched from one context (no I2C race).
 */

#include "vl53l5cx.h"

static void rangeTaskTrampoline(void* param) {
    ((VL53L5CX_Sensor*)param)->_rangeTaskLoop();
}

VL53L5CX_Sensor::VL53L5CX_Sensor(TwoWire& wirePort, GridMode mode)
    : _wire(wirePort)
    , _rangeTask(nullptr)
    , _pendingMode(mode)
    , _reconfigure(false)
    , _dataReady(false)
{
    _configureForMode(mode);
    memset((void*)_distances, 0, sizeof(_distances));
}

void VL53L5CX_Sensor::_configureForMode(GridMode mode) {
    _mode = mode;
    _zoneCount = (int)mode;  // enum value == logical zone count
    switch (mode) {
        case GRID_SINGLE: _width = 1; break;
        case GRID_2X2:    _width = 2; break;
        case GRID_4X4:    _width = 4; break;
        case GRID_8X8:    _width = 8; break;
    }
    // Only the full 8x8 grid needs the native 64-zone hardware mode (capped at
    // 15Hz). Every coarser grid runs on the faster 16-zone (4x4) hardware mode
    // and is down-sampled in software, so it ranges at ~30Hz.
    if (mode == GRID_8X8) {
        _hwResolution = 64;
        _hwWidth = 8;
        _rangingHz = 15;
        _pollDelayMs = 50;  // ~20Hz poll (sensor runs at 15Hz)
    } else {
        _hwResolution = 16;
        _hwWidth = 4;
        _rangingHz = 30;
        _pollDelayMs = 25;  // ~40Hz poll (sensor runs at 30Hz)
    }
}

void VL53L5CX_Sensor::_applyMode(GridMode mode) {
    _sensor.stopRanging();
    _configureForMode(mode);
    memset((void*)_distances, 0, sizeof(_distances));
    _dataReady = false;
    _sensor.setResolution(_hwResolution);
    _sensor.setRangingFrequency(_rangingHz);
    _sensor.startRanging();
}

bool VL53L5CX_Sensor::begin() {
    // The Wire bus has already been initialized by codegen for this port —
    // do NOT call _wire.begin() here, that would re-pinmux the bus and break
    // any other I2C device sharing this peripheral.
    Serial.println("Initializing VL53L5CX (this takes a few seconds)...");

    if (!_sensor.begin(0x29, _wire)) {
        Serial.println("VL53L5CX not found!");
        return false;
    }

    _sensor.setResolution(_hwResolution);
    _sensor.setRangingFrequency(_rangingHz);
    _sensor.startRanging();

    // Start background ranging task on Core 0
    xTaskCreatePinnedToCore(
        rangeTaskTrampoline,
        "VL53L5CX",
        4096,      // Needs more stack for the SparkFun library
        this,
        1,
        &_rangeTask,
        0
    );

    Serial.println("VL53L5CX initialized");
    return true;
}

void VL53L5CX_Sensor::setGridMode(GridMode mode) {
    // Hand the change off to the ranging task — it owns all sensor access, so
    // reconfiguring there avoids racing an in-flight I2C transaction.
    _pendingMode = mode;
    _reconfigure = true;
}

int16_t VL53L5CX_Sensor::getDistance(int zone) {
    if (zone < 0 || zone >= _zoneCount) return -1;
    return _distances[zone];
}

void VL53L5CX_Sensor::getDistanceGrid(int16_t* buffer) {
    memcpy(buffer, (const void*)_distances, sizeof(int16_t) * _zoneCount);
}

bool VL53L5CX_Sensor::isReady() {
    return _dataReady;
}

int16_t VL53L5CX_Sensor::getMinDistance() {
    int16_t minDist = 32767;
    for (int i = 0; i < _zoneCount; i++) {
        if (_distances[i] > 0 && _distances[i] < minDist) {
            minDist = _distances[i];
        }
    }
    return minDist;
}

int16_t VL53L5CX_Sensor::getMaxDistance() {
    int16_t maxDist = 0;
    for (int i = 0; i < _zoneCount; i++) {
        if (_distances[i] > maxDist) {
            maxDist = _distances[i];
        }
    }
    return maxDist;
}

// Down-sample the raw hardware grid (_hwWidth x _hwWidth) into the logical grid
// (_width x _width). For native modes (8x8, 4x4) this is a straight copy. For
// the coarser modes each logical zone reports the CLOSEST valid object in its
// block — the most useful value for presence/"how far is the nearest thing".
void VL53L5CX_Sensor::_updateGrid(int16_t* raw) {
    if (_width == _hwWidth) {
        for (int i = 0; i < _zoneCount; i++) {
            _distances[i] = raw[i];
        }
        return;
    }

    const int block = _hwWidth / _width;  // 4->2x2: block=2; 4->1x1: block=4
    for (int ly = 0; ly < _width; ly++) {
        for (int lx = 0; lx < _width; lx++) {
            int16_t best = 32767;
            for (int dy = 0; dy < block; dy++) {
                for (int dx = 0; dx < block; dx++) {
                    int16_t d = raw[(ly * block + dy) * _hwWidth + (lx * block + dx)];
                    if (d > 0 && d < best) best = d;
                }
            }
            // 0 means "nothing valid in this region" — matches how getMinDistance
            // treats 0-vs-positive, so downstream code stays consistent.
            _distances[ly * _width + lx] = (best == 32767) ? 0 : best;
        }
    }
}

// ========== Background task ==========

void VL53L5CX_Sensor::_rangeTaskLoop() {
    VL53L5CX_ResultsData results;

    while (true) {
        // Apply any pending resolution change here, where we're the only
        // context touching the sensor.
        if (_reconfigure) {
            _applyMode(_pendingMode);
            _reconfigure = false;
        }

        if (_sensor.isDataReady()) {
            if (_sensor.getRangingData(&results)) {
                _updateGrid(results.distance_mm);
                _dataReady = true;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(_pollDelayMs));
    }
}
