#!/usr/bin/env python3
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

dt = 0.02           
T  = 20.0         
N  = int(T / dt)

def board_angles(t):
    roll  = 10.0 * math.sin(0.4 * t) * math.pi / 180.0  
    pitch = 8.0  * math.sin(0.6 * t + 1.0) * math.pi / 180.0
    return roll, pitch

Kp_r, Kd_r = 4.0, 0.5   
Kp_p, Kd_p = 4.0, 0.5   

body_roll  = 0.0
body_pitch = 0.0
prev_er = 0.0
prev_ep = 0.0

log_t  = []
log_br = []
log_bp = []
log_rr = []
log_rp = []

for i in range(N):
    t = i * dt
    # góc ván
    board_roll, board_pitch = board_angles(t)

    # giả định IMU đo thân = góc ván + (thân lệch chút)
    imu_roll  = body_roll  + 0.0
    imu_pitch = body_pitch + 0.0

    # lỗi mong muốn: thân phải ngang (0,0)
    er = 0.0 - imu_roll
    ep = 0.0 - imu_pitch

    der = (er - prev_er) / dt
    dep = (ep - prev_ep) / dt
    prev_er, prev_ep = er, ep

    u_r = Kp_r * er + Kd_r * der
    u_p = Kp_p * ep + Kd_p * dep

    # hệ thống rất đơn giản: thân quay theo moment điều khiển + ảnh hưởng ván
    # ở đây ta coi thân muốn bám theo -góc ván + u
    alpha = 5.0  # hệ số bám ván
    body_roll  += (alpha * (board_roll  - body_roll)  + u_r) * dt
    body_pitch += (alpha * (board_pitch - body_pitch) + u_p) * dt

    log_t.append(t)
    log_br.append(body_roll)
    log_bp.append(body_pitch)
    log_rr.append(board_roll)
    log_rp.append(board_pitch)

# --------------- VẼ ANIMATION 2D -----------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

# vẽ board + body nhìn ngang (roll)
ax1.set_title("Roll (nghiêng trái/phải)")
ax1.set_xlim(-2, 2)
ax1.set_ylim(-1, 1)
ax1.set_aspect("equal")

board_line_roll, = ax1.plot([], [], lw=4, label="Board")
body_line_roll,  = ax1.plot([], [], lw=4, label="Body")
ax1.legend(loc="upper right")

# vẽ lịch sử góc
ax2.set_title("Góc theo thời gian")
ax2.set_xlim(0, T)
ax2.set_ylim(-20, 20)
ax2.set_xlabel("t (s)")
ax2.set_ylabel("deg")
br_plot, = ax2.plot([], [], label="Body roll")
rr_plot, = ax2.plot([], [], label="Board roll")
bp_plot, = ax2.plot([], [], label="Body pitch")
rp_plot, = ax2.plot([], [], label="Board pitch")
ax2.legend(loc="upper right")

def init():
    board_line_roll.set_data([], [])
    body_line_roll.set_data([], [])
    br_plot.set_data([], [])
    rr_plot.set_data([], [])
    bp_plot.set_data([], [])
    rp_plot.set_data([], [])
    return (board_line_roll, body_line_roll,
            br_plot, rr_plot, bp_plot, rp_plot)

def animate(frame):
    t = log_t[frame]
    br = log_br[frame]
    bp = log_bp[frame]
    rr = log_rr[frame]
    rp = log_rp[frame]

    # ván và thân là 2 đoạn thẳng dài 3 đơn vị
    L = 3.0
    # board roll
    x_board = np.array([-L/2, L/2])
    y_board = np.array([0.0, 0.0])
    Rb = np.array([[math.cos(rr), -math.sin(rr)],
                   [math.sin(rr),  math.cos(rr)]])
    xb, yb = Rb @ np.vstack((x_board, y_board))
    board_line_roll.set_data(xb, yb)

    # body roll
    Rbody = np.array([[math.cos(br), -math.sin(br)],
                      [math.sin(br),  math.cos(br)]])
    xb2, yb2 = Rbody @ np.vstack((x_board, y_board))
    body_line_roll.set_data(xb2, yb2)

    # update lịch sử
    t_arr = np.array(log_t[:frame+1])
    br_arr = np.rad2deg(np.array(log_br[:frame+1]))
    rr_arr = np.rad2deg(np.array(log_rr[:frame+1]))
    bp_arr = np.rad2deg(np.array(log_bp[:frame+1]))
    rp_arr = np.rad2deg(np.array(log_rp[:frame+1]))

    br_plot.set_data(t_arr, br_arr)
    rr_plot.set_data(t_arr, rr_arr)
    bp_plot.set_data(t_arr, bp_arr)
    rp_plot.set_data(t_arr, rp_arr)

    return (board_line_roll, body_line_roll,
            br_plot, rr_plot, bp_plot, rp_plot)

ani = FuncAnimation(fig, animate, frames=N,
                    init_func=init, interval=dt*1000, blit=True)

plt.tight_layout()
plt.show()
