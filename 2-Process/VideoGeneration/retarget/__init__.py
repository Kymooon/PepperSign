"""
PepperSign - Retargeting video -> gesto Pepper (BETA, fase F0).

Pipeline:
    video -> keypoint umani per frame (DWPose 2D / MediaPipe 3D)
          -> retargeting geometrico sugli angoli dei giunti di Pepper
          -> smoothing, limiti, riduzione a keyframe
          -> JSON "frames_v1" apribile nella GUI di Controll.

Moduli:
    pepper_kinematics  modello cinematico semplificato delle braccia di Pepper
    keypoints          formato comune dei keypoint + conversioni DWPose/MediaPipe
    depth              stima della profondita' da keypoint 2D (opzione A)
    retarget           keypoint 3D -> angoli dei giunti di Pepper
    postprocess        smoothing, keyframe, dt, export frames_v1
    f0                 script della fase di fattibilita'
"""
