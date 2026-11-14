/**
 * @file vl53l5cx.h
 * @brief VL53L5CX Multi-Resolution Time-of-Flight Distance Sensor for Athera
 *
 * Multi-zone ToF sensor with a SELECTABLE grid resolution. Trade spatial
 * detail for speed: a full 8x8 grid is the most detailed but slowest, while a
 * single point is the quickest way to answer "how far is the nearest thing".
 * Uses a background FreeRTOS task for continuous ranging — public getters
 * return cached distance values instantly.
 *
 * Grid modes (see GridMode):
 * - GRID_8X8    : 64 zones, ranges at 15Hz — full spatial detail (default)
 * - GRID_4X4    : 16 zones, ranges at 30Hz — coarser but ~2x faster
 * - GRID_2X2    : 4 zones,  ranges at 30Hz — quadrants, quick
 * - GRID_SINGLE : 1 zone,   ranges at 30Hz — one number, quickest
 *
 * The VL53L5CX hardware natively supports only 4x4 and 8x8. GRID_2X2 and
 * GRID_SINGLE run on the fast 4x4 hardware mode and are down-sampled in
 * software (each logical zone reports the CLOSEST object in its region), so
 * they are just as fast as GRID_4X4 while being simpler to consume.
 *
 * Range: up to 4000mm. Interface: I2C (via Wire).
 *
 * Note: This module uses the SparkFun VL53L5CX library, which talks to the
 * Arduino Wire library directly (not our I2CInterface abstraction). It accepts
 * a TwoWire& reference so it can share the per-port Wire instance that codegen
 * already initialized — it must NOT re-initialize the bus itself, or it will
 * clobber any other I2C device sharing that peripheral.
 *
 * Athera Connector:
 * - Line A: SDA
 * - Line B: SCL
 */

#ifndef VL53L5CX_MODULE_H
#define VL53L5CX_MODULE_H

#include <Arduino.h>
#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

class VL53L5CX_Sensor {
public:
    /**
     * @brief Selectable grid resolution. The enum value IS the logical zone count.
     *
     * Coarser grids range faster — pick the smallest grid that satisfies the
     * task. GRID_SINGLE is ideal for a quick "nearest object" reading; GRID_8X8
     * is best when the spatial layout of what's in front actually matters.
     */
    enum GridMode {
        GRID_SINGLE = 1,   // 1 zone  (1x1) — quickest, reports the closest object
        GRID_2X2    = 4,   // 4 zones (2x2) — quadrants
        GRID_4X4    = 16,  // 16 zones (4x4) — native fast hardware mode
        GRID_8X8    = 64,  // 64 zones (8x8) — full detail, slowest (default)
    };

    // Largest grid the sensor can produce — sizes the internal buffer.
    static constexpr int MAX_ZONES = 64;

    /**
     * @brief Construct VL53L5CX sensor
     * @param wirePort TwoWire instance for this port (Wire or Wire1), already
     *                 initialized by codegen with the port's SDA/SCL pins.
     * @param mode     Initial grid resolution (default GRID_8X8). Can also be
     *                 changed at runtime with setGridMode().
     */
    explicit VL53L5CX_Sensor(TwoWire& wirePort, GridMode mode = GRID_8X8);

    /**
     * @brief Initialize sensor, start ranging, and launch background task
     * @return true on success
     */
    bool begin();

    /**
     * @brief Change the grid resolution at runtime.
     *
     * Safe to call any time after begin() — the reconfiguration is applied by
     * the background ranging task, so the sensor (I2C) is only ever touched
     * from one context. Readings briefly report empty until the first frame
     * arrives in the new mode. Best called once in setup(); avoid calling it
     * every loop.
     * @param mode New grid resolution.
     */
    void setGridMode(GridMode mode);

    /** @brief Current grid mode. */
    GridMode getGridMode() const { return _mode; }

    /** @brief Number of logical zones in the current mode (1, 4, 16, or 64). */
    int zoneCount() const { return _zoneCount; }

    /** @brief Width of the current logical grid (1, 2, 4, or 8). zone = row*width + col. */
    int gridWidth() const { return _width; }

    /**
     * @brief Get distance for a specific zone
     * @param zone Zone index (row*gridWidth() + col, 0 to zoneCount()-1)
     * @return Distance in mm, or -1 if invalid zone
     */
    int16_t getDistance(int zone);

    /**
     * @brief Copy the full distance grid into buffer
     * @param buffer Array of at least zoneCount() int16_t values
     */
    void getDistanceGrid(int16_t* buffer);

    /** @brief Check if sensor has provided at least one reading */
    bool isReady();

    /** @brief Get minimum distance across all zones in mm */
    int16_t getMinDistance();

    /** @brief Get maximum distance across all zones in mm */
    int16_t getMaxDistance();

    // Background task function (public for static callback, do not call directly)
    void _rangeTaskLoop();

private:
    // Apply a grid mode to the sensor hardware (stop → set resolution/freq →
    // start). Called from begin() and from the ranging task on reconfigure.
    void _applyMode(GridMode mode);
    // Configure the derived fields (_mode, _zoneCount, _width, _hwWidth,
    // _hwResolution, _rangingHz, _pollDelayMs) for a mode without touching HW.
    void _configureForMode(GridMode mode);
    // Down-sample the raw hardware grid into the logical grid (_distances).
    void _updateGrid(int16_t* raw);

    TwoWire& _wire;
    SparkFun_VL53L5CX _sensor;
    TaskHandle_t _rangeTask;

    // These describe the active grid and are read cross-core by the public
    // getters while the ranging task may be rewriting them on a mode change,
    // so they are volatile (like _distances/_dataReady below).
    volatile GridMode _mode;   // current logical grid mode
    volatile int _zoneCount;   // logical zone count (1/4/16/64)
    volatile int _width;       // logical grid width (1/2/4/8)
    int _hwResolution;       // hardware resolution passed to the driver (16 or 64)
    int _hwWidth;            // hardware grid width (4 or 8)
    int _rangingHz;          // ranging frequency for the current mode
    int _pollDelayMs;        // task poll delay for the current mode

    volatile GridMode _pendingMode;  // requested by setGridMode(), applied by task
    volatile bool _reconfigure;      // set by setGridMode(), cleared by task

    volatile int16_t _distances[MAX_ZONES];  // logical grid values (mm)
    volatile bool _dataReady;
};

#endif // VL53L5CX_MODULE_H
