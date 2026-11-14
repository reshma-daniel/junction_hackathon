/**
 * @file dc_motor.h
 * @brief DC Motor Driver Module (H-Bridge) for Athera
 *
 * Controls a DC motor using IN1/IN2 H-bridge inputs.
 * IN1 and IN2 control direction and speed (via PWM).
 *
 * Control logic:
 * - IN1=HIGH, IN2=LOW  -> Forward
 * - IN1=LOW,  IN2=HIGH -> Reverse
 * - IN1=LOW,  IN2=LOW  -> Coast/Stop
 * - IN1=HIGH, IN2=HIGH -> Brake
 *
 * Athera Connector:
 * - Pin 1: 12V (motor power)
 * - Pin 4: GND
 * - Pin 5: IN1 (Data Line A)
 * - Pin 6: IN2 (Data Line B)
 */

#ifndef DC_MOTOR_MODULE_H
#define DC_MOTOR_MODULE_H

#include <Arduino.h>

class DCMotor {
public:
    /**
     * @brief Construct DC motor controller
     * @param in1Pin GPIO for IN1
     * @param in2Pin GPIO for IN2
     */
    DCMotor(int in1Pin, int in2Pin);

    /**
     * @brief Initialize motor pins
     * @param pwmFreq PWM frequency in Hz (default 25000 — above the
     *                audible range to avoid motor squeal)
     */
    void begin(uint32_t pwmFreq = 25000);

    /**
     * @brief Set motor speed and direction
     * @param speed -255 to +255 (negative = reverse)
     */
    void setSpeed(int16_t speed);

    /**
     * @brief Run motor forward
     * @param speed 0-255
     */
    void forward(uint8_t speed = 255);

    /**
     * @brief Run motor in reverse
     * @param speed 0-255
     */
    void reverse(uint8_t speed = 255);

    /**
     * @brief Stop motor (coast)
     */
    void stop();

    /**
     * @brief Brake motor (active stop)
     */
    void brake();

    /**
     * @brief Get current speed setting
     */
    int16_t getSpeed() const { return _currentSpeed; }

private:
    int _in1Pin, _in2Pin;
    int16_t _currentSpeed;

#ifdef ESP32
    int _pwmChannel1, _pwmChannel2;
    bool _useHwPwm;  // true if LEDC channels were available
#endif
};

#endif // DC_MOTOR_MODULE_H
