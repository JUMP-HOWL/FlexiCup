#!/bin/bash

# 视频优化脚本
# 压缩视频文件以提高网页加载速度

# 清理环境变量，避免conda库冲突
unset LD_LIBRARY_PATH
unset CONDA_PREFIX
unset CONDA_DEFAULT_ENV

VIDEO_DIR="./static/video/websitevideo"
OPTIMIZED_DIR="./static/video/optimized"

# 创建优化视频目录
mkdir -p "$OPTIMIZED_DIR"

echo "开始优化视频文件..."

# 使用静态编译的ffmpeg，避免库冲突
FFMPEG_PATH="./ffmpeg-static"

# 检查ffmpeg是否可用
if [ ! -f "$FFMPEG_PATH" ]; then
    echo "下载静态编译的ffmpeg..."
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -O /tmp/ffmpeg-static.tar.xz
    tar -xf /tmp/ffmpeg-static.tar.xz -C /tmp
    cp /tmp/ffmpeg-*/ffmpeg ./ffmpeg-static
    chmod +x ./ffmpeg-static
fi

# 遍历所有mp4文件
for video in "$VIDEO_DIR"/*.mp4; do
    if [ -f "$video" ] && [[ "$video" != *"_original.mp4" ]] && [[ "$video" != *"overview_h264.mp4" ]]; then
        filename=$(basename "$video")
        output="$OPTIMIZED_DIR/$filename"
        
        echo "正在优化: $filename"
        
        # 获取原文件大小
        original_size=$(du -h "$video" | cut -f1)
        
        # FFmpeg优化参数:
        # -c:v libx264: 使用H.264编码器
        # -crf 28: 恒定质量因子 (18-28范围，数值越小质量越高)
        # -preset medium: 编码速度预设
        # -c:a aac: 音频编码器
        # -b:a 128k: 音频比特率
        # -movflags +faststart: 优化网络播放
        
        env -i PATH=/usr/bin:/bin "$FFMPEG_PATH" -i "$video" \
            -c:v libx264 \
            -crf 28 \
            -preset medium \
            -c:a aac \
            -b:a 128k \
            -movflags +faststart \
            -y "$output"
        
        if [ $? -eq 0 ]; then
            # 获取优化后文件大小
            optimized_size=$(du -h "$output" | cut -f1)
            echo "✓ $filename 优化完成: $original_size -> $optimized_size"
        else
            echo "✗ $filename 优化失败"
        fi
    fi
done

echo "视频优化完成！"
echo "原始视频在: $VIDEO_DIR"
echo "优化视频在: $OPTIMIZED_DIR"