#include "camera.h"
#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/ledc.h"
#include "led.h"
#include "time.h"
#include "sys/time.h"
#include "netinet/in.h"
#include "arpa/inet.h"
#include "errno.h"

/* 外部变量声明 */
extern uint8_t ip_third_octet;

/* 外部函数声明 */
extern void writeWifiInfo(unsigned char *wifiName, unsigned char *wifiPassword,
                          unsigned char *udpIP, unsigned int udpPORT,
                          unsigned char *wifiConnectState);

/* 外部变量声明 */
extern unsigned char wifiName[20];
extern unsigned char wifiPassword[20];

/* 外部函数声明 */
extern void wifi_init_sta(char *WIFI_Name, char *WIFI_PassWord, char *isConnected);

/* 外部变量声明 */
extern char isConnectedFlag;

/* ---------------------- 关键参数调整（网络/相机） ---------------------- */
/* 理由：64KB 的单包在某些主机/链路下更容易顶满缓冲；改 16KB + 轻微延时更稳 */
#define UDP_SEND_MAX_LEN (64 * 1024)

/* 说明：若你的工程里已经有这些宏，请只改数值，别重复定义。*/
#define RMT_LED_STRIP_RESOLUTION_HZ 10000000 // 10MHz resolution
#define RMT_LED_STRIP_GPIO_NUM 38
#define EXAMPLE_LED_NUMBERS 36
#define EXAMPLE_CHASE_SPEED_MS 0

/* 降低 LED 亮度，减少供电波动（需要与你实际 LED 电源核对） */
#define LED_MAX_LEVEL 255 // 原来你写 255；如果需要更亮再逐步加

/* ---------------------- LED 模式常量 ---------------------- */
#define FLASH_MODE 1
#define FIXED_MODE 0
#define WAIT_MODE 2

static const char *LED = "led";
uint8_t led_strip_pixels[EXAMPLE_LED_NUMBERS * 3];

/* ---------------------- 互斥/队列/任务句柄 ---------------------- */
/* 新增：保护 sensor_t 的寄存器访问，避免与 CSI 采集时序冲突 */
SemaphoreHandle_t sensorMutex = NULL;

QueueHandle_t redQueue;
QueueHandle_t greenQueue;
QueueHandle_t blueQueue;
SemaphoreHandle_t flashModeSemaphore;
QueueHandle_t brightnessQueue;
QueueHandle_t flashIntervalQueue;
QueueHandle_t ledControlQueue;

bool isFlashMode = false;
bool isLedOn = false;
_deviceInfo deviceAttributeInfo = {
    .UDP_serverIP = "",
    .UDP_serverPort = 8000};

nvs_handle_t nvsHandle = {0}; /* NVS读写数据句柄 */
struct tm timeinfo = {0};
static const char *UDP = "UDP";
TaskHandle_t ledTaskHandle;
TaskHandle_t cameraTaskHandle;            /* 摄像头采任务的句柄 */
void udpReceive_task(void *pvParameters); /* udp数据接收任务 */
void camera_task(void *pvParameters);
/* socket使用的相关变量 */
int addr_family = 0;
int ip_protocol = 0;
struct sockaddr_in dest_addr;
int udpSock = 0;
/* 时间戳变量 */
unsigned long int sysStartTimeStamp = 0;
unsigned long int nowTimeStamp = 0;
/* 系统指示灯变量 */
unsigned char netOnlineFlag;
unsigned char workFlag;
/*MY*/
#define CAM_PIN_PWDN (-1)
#define CAM_PIN_RESET (-1) // software reset will be performed
#define CAM_PIN_XCLK (11)
#define CAM_PIN_SIOD (4)
#define CAM_PIN_SIOC (5)

#define CAM_PIN_D7 (10)
#define CAM_PIN_D6 (12)
#define CAM_PIN_D5 (13)
#define CAM_PIN_D4 (15)
#define CAM_PIN_D3 (17)
#define CAM_PIN_D2 (21)
#define CAM_PIN_D1 (18)
#define CAM_PIN_D0 (16)
#define CAM_PIN_VSYNC (6)
#define CAM_PIN_HREF (9)
#define CAM_PIN_PCLK (14)
/*KIT*/
// #define CAM_PIN_PWDN    (-1)
// #define CAM_PIN_RESET   (-1) //software reset will be performed
// #define CAM_PIN_XCLK    (15)
// #define CAM_PIN_SIOD    ( 4)
// #define CAM_PIN_SIOC    ( 5)

// #define CAM_PIN_D7      (16)
// #define CAM_PIN_D6      (17)
// #define CAM_PIN_D5      (18)
// #define CAM_PIN_D4      (12)
// #define CAM_PIN_D3      (10)
// #define CAM_PIN_D2      ( 8)
// #define CAM_PIN_D1      ( 9)
// #define CAM_PIN_D0      (11)
// #define CAM_PIN_VSYNC   ( 6)
// #define CAM_PIN_HREF    ( 7)
// #define CAM_PIN_PCLK    (13)
static const char *camera = "camera";

/* ---------------------- 相机配置（关键改动） ---------------------- */
/* 说明：
 * 1) fb_count 改 2（双缓冲）
 * 2) grab_mode 改 LATEST（丢旧保新）
 * 3) jpeg_quality 提高数值 = 降低质量（默认从 10 调到 20，更稳；如仍卡，再调大）
 * 4) frame_size 保持 XGA（你的目标是 1024x768），如仍卡可临时降到 SVGA 验证链路。
 */
static camera_config_t camera_config = {
    .pin_pwdn = CAM_PIN_PWDN,
    .pin_reset = CAM_PIN_RESET,
    .pin_xclk = CAM_PIN_XCLK,
    .pin_sccb_sda = CAM_PIN_SIOD,
    .pin_sccb_scl = CAM_PIN_SIOC,

    .pin_d7 = CAM_PIN_D7,
    .pin_d6 = CAM_PIN_D6,
    .pin_d5 = CAM_PIN_D5,
    .pin_d4 = CAM_PIN_D4,
    .pin_d3 = CAM_PIN_D3,
    .pin_d2 = CAM_PIN_D2,
    .pin_d1 = CAM_PIN_D1,
    .pin_d0 = CAM_PIN_D0,
    .pin_vsync = CAM_PIN_VSYNC,
    .pin_href = CAM_PIN_HREF,
    .pin_pclk = CAM_PIN_PCLK,

    .xclk_freq_hz = 24 * 1000 * 1000, // 假设为 OV5640；如为别的传感器，请同学核对数据手册
    .ledc_timer = LEDC_TIMER_0,
    .ledc_channel = LEDC_CHANNEL_0,

    .pixel_format = PIXFORMAT_JPEG,
    .frame_size = FRAMESIZE_XGA,     // 1024x768
    .jpeg_quality = 10,              // 原来是 10；数值越大码率越低，网络更稳
    .fb_count = 2,                   // ★改为 2
    .grab_mode = CAMERA_GRAB_LATEST, // ★改为 LATEST（丢旧保新）
};

/* ---------------------- 暗/明两套曝光模式（联动 LED） ---------------------- */
/* 说明：
 * - 目的：避免关灯后 AEC 把曝光拉到极限，导致帧率跌至 1~2fps 甚至更低。
 * - 流程：先暂时关 AEC => 设置一组安全曝光/增益 => 等 150ms 光照稳定 => 再开 AEC 细调。
 * - 数值为经验值，需要你的同学根据现场亮度/镜头/FPS微调。
 * - 若希望完全手动：最后一步不要再开 AEC（把 set_exposure_ctrl(s,1) 改成 0），改 PC 端下发 setExposure。
 */
static void apply_light_mode(bool led_on)
{
    if (!sensorMutex)
        return;

    xSemaphoreTake(sensorMutex, portMAX_DELAY);
    sensor_t *s = esp_camera_sensor_get();
    if (s)
    {
        /* 先关自动曝光，避免在积分关键时段改寄存器 */
        s->set_exposure_ctrl(s, 0);
        s->set_gain_ctrl(s, 1); // 允许 AGC
        s->set_aec2(s, 1);      // OV5640 建议打开；若非 OV5640，请同学核对

        if (led_on)
        {
            /* 开灯 = 高照模式：相对短曝光，降低增益 */
            s->set_aec_value(s, 30); // 经验值，现场需微调
            s->set_agc_gain(s, 4);
            s->set_gainceiling(s, GAINCEILING_16X);
            s->set_ae_level(s, 0);
            s->set_brightness(s, 0);
        }
        else
        {
            /* 关灯 = 低照模式：限制最大曝光，主要靠增益，避免帧率塌陷 */
            s->set_aec_value(s, 260); // 不要太大，避免<~10-15fps
            s->set_agc_gain(s, 12);
            s->set_gainceiling(s, GAINCEILING_64X);
            s->set_ae_level(s, 0);
            s->set_brightness(s, 0);
        }

        /* 等待光照/RGB ISP 稳定（数值可 100~200ms 之间试） */
        vTaskDelay(150 / portTICK_PERIOD_MS);

        /* 方案A：重新打开 AEC，让其在合理区间内微调；
           若想全手动，请改为 0，并改由上位机 setExposure 指令细调 */
        s->set_exposure_ctrl(s, 1);
    }
    xSemaphoreGive(sensorMutex);
}

void sntp_Init(void) /* 获取实时网络时间 */
{
    /* 使用多个sntp服务器时，请在 make menuconfig -> Component config -> LWIP -> SNTP -> Maximum bumber of NTP servers 修改为 所使用的个数 */
    sntp_stop();
    ESP_LOGI("sntp", "start.");
    sntp_setoperatingmode(SNTP_OPMODE_POLL); // 设置单播模式
    sntp_setservername(0, "cn.ntp.org.cn");  // 设置访问服务器
    sntp_setservername(1, "ntp1.aliyun.com");
    sntp_setservername(2, "pool.ntp.org");
    sntp_setservername(3, "210.72.145.44"); // 国家授时中心服务器 IP 地址
    setenv("TZ", "CST-8", 1);               // 东八区
    tzset();                                // 更新本地C库时间
    sntp_init();                            // 初始化

    // 延时等待SNTP初始化完成
    do
    {
        vTaskDelay(1000 / portTICK_PERIOD_MS);
        ESP_LOGI("sntp", "wait for wifi sntp sync time---------------------");
    } while (sntp_get_sync_status() == SNTP_SYNC_STATUS_RESET);

    // 成功获取网络时间后停止NTP请求，不然设备重启后会造成获取网络时间失败的现象
    // 大概是服务器时根据心跳时间来删除客户端的，如果不是stop结束的客户端，下次连接服务器时就会出错
    sntp_stop();
    ESP_LOGI("sntp", "sntp stop.");
}

void get_time(void)
{
    time_t now;
    time(&now); // 获取网络时间, 64bit的秒计数

    localtime_r(&now, &timeinfo); // 转换成具体的时间参数
    ESP_LOGI("sntp", "%4d-%02d-%02d %02d:%02d:%02d week:%d", timeinfo.tm_year + 1900, timeinfo.tm_mon + 1,
             timeinfo.tm_mday, timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec, timeinfo.tm_wday);
}

/* 读取储存的摄像头信息，进行初始化配置 */
void cameraSetConfig(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND)
    {
        // NVS partition was truncated and needs to be erased
        // Retry nvs_flash_init
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(nvs_open("deviceInfo", NVS_READWRITE, &nvsHandle));

    /* 先读NVS指定键值对中是否有数据 */
    unsigned int readNvsLen = 0;
    err = nvs_get_str(nvsHandle, "deviceState", NULL, &readNvsLen); /* 判断当前设备的状态 */
    char devideState[10];
    if (readNvsLen > 0) /* 有数据 */
    {
        readNvsLen = 10;
        memset(devideState, 0, 10);
        err = nvs_get_str(nvsHandle, "deviceState", devideState, &readNvsLen); /* 读取保存在nvs中的设备状态*/
        if (strcmp(devideState, "online") == 0)                                /* 设备状态就绪,开始读取保存的参数数据 */
        {
            readNvsLen = 0;
            ESP_ERROR_CHECK(nvs_get_str(nvsHandle, "deviceID", NULL, &readNvsLen)); /* 读取设备ID */
            if (readNvsLen > 0)                                                     /* 有数据，那么就读取 */
            {
                readNvsLen = sizeof(deviceAttributeInfo.deviceID);
                err = nvs_get_str(nvsHandle, "deviceID", deviceAttributeInfo.deviceID, &readNvsLen); /* 读取保存在nvs中的设备ID */
                ESP_LOGI("nvs", "deviceID is %s,len = %d", deviceAttributeInfo.deviceID, readNvsLen - 1);
            }

            uint32_t out_value;
            ESP_ERROR_CHECK(nvs_get_u32(nvsHandle, "setVideoTime", &out_value)); /* 读取保存在nvs中的录像时间 */
            deviceAttributeInfo.scheduledDeletion = out_value;
            ESP_LOGI("nvs", "scheduledDeletion = %d.\n", deviceAttributeInfo.scheduledDeletion);

            readNvsLen = 0;
            err = nvs_get_str(nvsHandle, "picFormat", NULL, &readNvsLen); /* 读取设备ID */
            if (err != ESP_OK)
            {
                strcpy(deviceAttributeInfo.picFormat, "PIXFORMAT_JPEG");
                camera_config.pixel_format = PIXFORMAT_JPEG;
                ESP_ERROR_CHECK(nvs_set_str(nvsHandle, "picFormat", (char *)deviceAttributeInfo.picFormat)); /* 写入数据 */
                ESP_ERROR_CHECK(nvs_commit(nvsHandle));                                                      /* 确认数据写入 */
            }
            else
            {
                if (readNvsLen > 0) /* 有数据，那么就读取 */
                {
                    readNvsLen = sizeof(deviceAttributeInfo.picFormat);
                    err = nvs_get_str(nvsHandle, "picFormat", deviceAttributeInfo.picFormat, &readNvsLen); /* 读取保存在nvs中的设备ID */
                    ESP_LOGI("nvs", "picFormat is %s,len = %d", deviceAttributeInfo.picFormat, readNvsLen - 1);

                    if (strcmp((char *)deviceAttributeInfo.picFormat, (char *)"PIXFORMAT_JPEG") == 0)
                    {
                        camera_config.pixel_format = PIXFORMAT_JPEG;
                    }
                    else
                    {
                        camera_config.pixel_format = PIXFORMAT_JPEG;
                    }
                }
            }

            err = nvs_get_u32(nvsHandle, "picQuality", &out_value); /* 读取保存在nvs中的JPEG图像质量 */
            if (err != ESP_OK)
            {
                deviceAttributeInfo.jpegQuality = 10; // 网络优化：适当降低质量以减少文件大小
                camera_config.jpeg_quality = deviceAttributeInfo.jpegQuality;
                uint32_t write_value = deviceAttributeInfo.jpegQuality;
                ESP_ERROR_CHECK(nvs_set_u32(nvsHandle, "picQuality", write_value)); /* 写入数据 */
                ESP_ERROR_CHECK(nvs_commit(nvsHandle));                             /* 确认数据写入 */
            }
            else
            {
                deviceAttributeInfo.jpegQuality = out_value;
                ESP_LOGI("nvs", "jpegQuality = %d.\n", deviceAttributeInfo.jpegQuality);
            }

            err = nvs_get_u32(nvsHandle, "picSize", &out_value); /* 读取保存在nvs中的图像大小 */
            if (err != ESP_OK)
            {
                camera_config.frame_size = FRAMESIZE_SXGA; // 设置默认分辨率为UXGA
                uint32_t write_value = camera_config.frame_size;
                ESP_ERROR_CHECK(nvs_set_u32(nvsHandle, "picSize", write_value)); /* 写入数据 */
                ESP_ERROR_CHECK(nvs_commit(nvsHandle));                          /* 确认数据写入 */
            }
            else
            {
                camera_config.frame_size = out_value;
                ESP_LOGI("nvs", "frame_size = %d.\n", camera_config.frame_size);
            }

            nvs_close(nvsHandle);

            err = nvs_open("wifiInfo", NVS_READWRITE, &nvsHandle);
            if (err != ESP_OK)
            {
                printf("Error (%s) opening NVS handle!", esp_err_to_name(err));
            }

            readNvsLen = 0;
            err = nvs_get_str(nvsHandle, "udpIP", NULL, &readNvsLen); /* 读取udp地址 */
            if (readNvsLen > 0)                                       /* 有数据，那么就读取 */
            {
                readNvsLen = sizeof(deviceAttributeInfo.UDP_serverIP);
                err = nvs_get_str(nvsHandle, "udpIP", deviceAttributeInfo.UDP_serverIP, &readNvsLen); /* 读取保存在nvs中的udp ip */
                ESP_LOGI("nvs", "UDP_serverIP is %s,len = %d", deviceAttributeInfo.UDP_serverIP, readNvsLen - 1);
            }

            out_value = 0;
            err = nvs_get_u32(nvsHandle, "udpPORT", &out_value); /* 读取udp地址 */
            deviceAttributeInfo.UDP_serverPort = out_value;
            ESP_LOGI("nvs", "UDP_serverPort = %d.", deviceAttributeInfo.UDP_serverPort);
            nvs_close(nvsHandle);
        }
        else
        {
            strcpy(devideState, "");                                  /* 写入空数据 */
            err = nvs_set_str(nvsHandle, "deviceState", devideState); /* 写入数据 */
            if (err == ESP_OK)
            {
                ESP_LOGI("nvs", "set deviceID success!\n");
            }
            else
            {
                ESP_LOGI("nvs", "set deviceID fail!\n");
            }
            err = nvs_commit(nvsHandle); /* 确认数据写入 */
            if (err != ESP_OK)
            {
                ESP_LOGI("nvs", "nvs_commit Failed!");
            }
            else
            {
                ESP_LOGI("nvs", "nvs_commit Done!");
            }
        }
    }
    else /* 读取设备状态，未就绪 */
    {
        sntp_Init(); /* 利用sntp定时器获取时间 */
        get_time();  /* 获取时间 */
        strcpy(devideState, "online");
        err = nvs_set_str(nvsHandle, "deviceState", devideState); /* 写入设备状态，就绪 */
        if (err == ESP_OK)
        {
            ESP_LOGI("nvs", "set deviceState success!\n");
        }
        else
        {
            ESP_LOGI("nvs", "set deviceState fail!\n");
        }
        memset(deviceAttributeInfo.deviceID, 0, sizeof(deviceAttributeInfo.deviceID));
        sprintf(deviceAttributeInfo.deviceID, "%04d%02d%02d%02d%02d%02d", timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec); /* 年月日时分秒 */
        ESP_LOGI("nvs", "set data %s .\n", deviceAttributeInfo.deviceID);
        err = nvs_open("deviceInfo", NVS_READWRITE, &nvsHandle);
        err = nvs_set_str(nvsHandle, "deviceID", deviceAttributeInfo.deviceID); /* 写入设备ID */
        if (err == ESP_OK)
        {
            ESP_LOGI("nvs", "set deviceID success!\n");
        }
        else
        {
            ESP_LOGI("nvs", "set deviceID fail!\n");
        }

        deviceAttributeInfo.scheduledDeletion = 3600 * 24 * 15;
        err = nvs_set_u32(nvsHandle, "setVideoTime", deviceAttributeInfo.scheduledDeletion); /* 写入录像时间 */
        if (err == ESP_OK)
        {
            ESP_LOGI("nvs", "set setVideoTime success!\n");
        }
        else
        {
            ESP_LOGI("nvs", "set setVideoTime fail!\n");
        }

        err = nvs_commit(nvsHandle); /* 确认数据写入 */
        if (err != ESP_OK)
        {
            ESP_LOGI("nvs", "nvs_commit Failed!");
        }
        else
        {
            ESP_LOGI("nvs", "nvs_commit Done!");
        }

        nvs_close(nvsHandle);
        esp_restart(); /* 重启设备 */
    }

    nvs_close(nvsHandle);
}

void getDeviceInfo(void)
{
    switch (camera_config.pixel_format) /* 判断设置的图片格式 */
    {
    case PIXFORMAT_RGB565:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        sprintf(deviceAttributeInfo.picFormat, "%s", "PIXFORMAT_RGB565");
        break;
    case PIXFORMAT_YUV422:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        sprintf(deviceAttributeInfo.picFormat, "%s", "PIXFORMAT_YUV422");
        break;
    case PIXFORMAT_YUV420:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        sprintf(deviceAttributeInfo.picFormat, "%s", "PIXFORMAT_YUV420");
        break;
    case PIXFORMAT_GRAYSCALE:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        sprintf(deviceAttributeInfo.picFormat, "%s", "PIXFORMAT_GRAYSCALE");
        break;
    case PIXFORMAT_JPEG:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        sprintf(deviceAttributeInfo.picFormat, "%s", "PIXFORMAT_JPEG");
        break;
    case PIXFORMAT_RGB888:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        sprintf(deviceAttributeInfo.picFormat, "%s", "PIXFORMAT_RGB888");
        break;
    default:
        memset(deviceAttributeInfo.picFormat, 0, 20); /* 清空数组，长度20 */
        break;
    }
    switch (camera_config.frame_size) /* 判断设置的图片大小 */
    {
    case FRAMESIZE_QVGA:
        deviceAttributeInfo.picWidth = 320;
        deviceAttributeInfo.picHeight = 240;
        break;
    case FRAMESIZE_VGA:
        deviceAttributeInfo.picWidth = 640;
        deviceAttributeInfo.picHeight = 480;
        break;
    case FRAMESIZE_SVGA: // 添加SVGA选项
        deviceAttributeInfo.picWidth = 800;
        deviceAttributeInfo.picHeight = 600;
        break;
    case FRAMESIZE_XGA: // 添加XGA选项
        deviceAttributeInfo.picWidth = 1024;
        deviceAttributeInfo.picHeight = 768;
        break;
    case FRAMESIZE_SXGA: // 添加SXGA选项
        deviceAttributeInfo.picWidth = 1280;
        deviceAttributeInfo.picHeight = 1024;
        break;
    case FRAMESIZE_UXGA:
        deviceAttributeInfo.picWidth = 1600;
        deviceAttributeInfo.picHeight = 1200;
        break;
    default:
        // 默认使用SXGA分辨率（与当前设置保持一致）
        deviceAttributeInfo.picWidth = 640;
        deviceAttributeInfo.picHeight = 480;
        break;
    }
    deviceAttributeInfo.jpegQuality = camera_config.jpeg_quality;
}
/* ---------------------- camera_task（关键改动：日志/看门狗/分片节奏） ---------------------- */
void camera_task(void *pvParameters)
{
    camera_fb_t *pic;
    esp_camera_deinit();
    esp_err_t err = esp_camera_init(&camera_config);
    if (err != ESP_OK)
    {
        ESP_LOGE(camera, "Camera Init Failed");
        return;
    }

    getDeviceInfo(); /* 获取配置信息 */

    /* 动态帧率上限（防止发包过快也有助于稳态） */
    TickType_t lastFrameTime = xTaskGetTickCount();
    const TickType_t minFrameInterval = pdMS_TO_TICKS(50); // 20fps 上限

    /* 看门狗：若长时间拿不到帧则软重启摄像头 */
    TickType_t lastOkTs = xTaskGetTickCount();

    while (1)
    {
        /* 帧率节流 */
        TickType_t now = xTaskGetTickCount();
        if ((now - lastFrameTime) < minFrameInterval)
        {
            vTaskDelay(minFrameInterval - (now - lastFrameTime));
        }
        lastFrameTime = xTaskGetTickCount();

        pic = esp_camera_fb_get();
        if (pic != NULL)
        {
            /* 统计帧间隔/帧长，便于验证关灯后是否暴涨 */
            static TickType_t last_ts = 0;
            TickType_t tnow = xTaskGetTickCount();
            uint32_t dt_ms = last_ts ? (tnow - last_ts) * portTICK_PERIOD_MS : 0;
            last_ts = tnow;
            ESP_LOGI("cam", "len=%u, dt=%lu ms", (unsigned)pic->len, (unsigned long)dt_ms);

            /* 发送前置头信息 */
            unsigned int preSendPicLen = pic->len;
            unsigned char *startPalce = pic->buf;

            char picInfo[100];
            sprintf(picInfo, "%s,%d,%ld,%s", "frameData", pic->len, esp_log_timestamp(), deviceAttributeInfo.deviceID);
            sendto(udpSock, picInfo, strlen(picInfo), 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
            vTaskDelay(5 / portTICK_PERIOD_MS);

            /* 分片发送：16KB 一片，中间加 1ms 呼吸，避免堆积 */
            if (preSendPicLen > UDP_SEND_MAX_LEN)
            {
                int sendCnt = 0;
                while (UDP_SEND_MAX_LEN * (sendCnt + 1) < preSendPicLen)
                {
                    sendto(udpSock, startPalce + (UDP_SEND_MAX_LEN * sendCnt), UDP_SEND_MAX_LEN, 0,
                           (struct sockaddr *)&dest_addr, sizeof(dest_addr));
                    vTaskDelay(1 / portTICK_PERIOD_MS); // ★新增：轻微间隔
                    sendCnt++;
                }
                sendto(udpSock, startPalce + (UDP_SEND_MAX_LEN * sendCnt),
                       preSendPicLen % UDP_SEND_MAX_LEN, 0,
                       (struct sockaddr *)&dest_addr, sizeof(dest_addr));
                vTaskDelay(1 / portTICK_PERIOD_MS); // ★新增
            }
            else
            {
                sendto(udpSock, startPalce, preSendPicLen, 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
                // 不再额外延时
            }

            /* 定时删除逻辑保持原样…… */
            nowTimeStamp = esp_log_timestamp();
            if (((nowTimeStamp / 1000 - sysStartTimeStamp / 1000)) >= deviceAttributeInfo.scheduledDeletion)
            {
                memset(picInfo, 0, sizeof(picInfo));
                sprintf(picInfo, "%s,%s", "deleteVideo", deviceAttributeInfo.deviceID);
                sendto(udpSock, picInfo, strlen(picInfo), 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
                vTaskDelay(10 / portTICK_PERIOD_MS);
                sysStartTimeStamp = nowTimeStamp;
            }

            esp_camera_fb_return(pic);
            lastOkTs = xTaskGetTickCount();
        }
        else
        {
            ESP_LOGW("camera", "esp_camera_fb_get() == NULL");
            sendto(udpSock, "error", 5, 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
            vTaskDelay(200 / portTICK_PERIOD_MS);
            workFlag = 0;
        }

        /* 看门狗：>1500ms 未成功抓帧，软复位摄像头（可按需关闭） */
        if ((xTaskGetTickCount() - lastOkTs) * portTICK_PERIOD_MS > 1500)
        {
            ESP_LOGW("camera", "No frame for >1500ms, reinit camera");
            esp_camera_deinit();
            vTaskDelay(50 / portTICK_PERIOD_MS);
            esp_err_t re = esp_camera_init(&camera_config);
            if (re == ESP_OK)
                lastOkTs = xTaskGetTickCount();
            else
                ESP_LOGE("camera", "reinit failed: %d", re);
        }
    }
}

/* ---------------------- udpReceive_task（关键改动：联动曝光 + 互斥） ---------------------- */
void udpReceive_task(void *pvParameters)
{
    static unsigned char rx_buffer[100];
    struct sockaddr_storage source_addr;
    socklen_t socklen = sizeof(source_addr);

    while (1)
    {
        int len = recvfrom(udpSock, rx_buffer, sizeof(rx_buffer) - 1, 0, (struct sockaddr *)&source_addr, &socklen);
        if (len > 0)
        {
            rx_buffer[len] = 0;
            ESP_LOGI(UDP, "Received %d bytes", len);

            if (strstr((char *)rx_buffer, "setLedState") != NULL)
            {
                ESP_LOGI(UDP, "%s", rx_buffer);

                char *tempString = strtok((char *)rx_buffer, ",");
                tempString = strtok(NULL, ",");
                bool newLedState = atoi(tempString);

                /* ★ 先联动曝光（锁-切-解锁）再切 LED，避免 AEC 在强/弱光跳变时拉爆曝光 */
                apply_light_mode(newLedState);

                /* 再切 LED（仍走队列） */
                if (xQueueSend(ledControlQueue, &newLedState, portMAX_DELAY) != pdPASS)
                {
                    ESP_LOGE(LED, "Failed to send LED state to queue");
                }
            }
            else if (strstr((char *)rx_buffer, "setExposure") != NULL)
            {
                ESP_LOGI(UDP, "%s", rx_buffer);
                char *tempString = strtok((char *)rx_buffer, ",");
                tempString = strtok(NULL, ",");
                int aec_enable = atoi(tempString);
                tempString = strtok(NULL, ",");
                int aec_value = atoi(tempString);
                tempString = strtok(NULL, ",");
                int agc_enable = atoi(tempString);
                tempString = strtok(NULL, ",");
                int agc_gain = atoi(tempString);
                tempString = strtok(NULL, ",");
                int brightness = atoi(tempString);

                /* ★ 互斥保护：避免与采集并发 */
                xSemaphoreTake(sensorMutex, portMAX_DELAY);
                sensor_t *s = esp_camera_sensor_get();
                if (s != NULL)
                {
                    s->set_exposure_ctrl(s, aec_enable);
                    s->set_aec_value(s, aec_value);
                    s->set_gain_ctrl(s, agc_enable);
                    s->set_agc_gain(s, agc_gain);
                    s->set_brightness(s, brightness);
                    xSemaphoreGive(sensorMutex);

                    ESP_LOGI(UDP, "Exposure updated: AEC=%d, AEC_Value=%d, AGC=%d, AGC_Gain=%d, Bright=%d",
                             aec_enable, aec_value, agc_enable, agc_gain, brightness);
                    char ack_msg[50];
                    sprintf(ack_msg, "Exposure settings applied");
                    sendto(udpSock, ack_msg, strlen(ack_msg), 0, (struct sockaddr *)&source_addr, socklen);
                }
                else
                {
                    xSemaphoreGive(sensorMutex);
                    ESP_LOGE(UDP, "Failed to get camera sensor");
                    char error_msg[50];
                    sprintf(error_msg, "Failed to get camera sensor");
                    sendto(udpSock, error_msg, strlen(error_msg), 0, (struct sockaddr *)&source_addr, socklen);
                }
            }
        }
    }
}

/* ---------------------- led_task（关键改动：降低满功率） ---------------------- */
void led_task(void *pvParameters)
{
    ESP_LOGI(LED, "Create RMT TX channel");

    rmt_channel_handle_t led_chan = 0;
    rmt_tx_channel_config_t tx_chan_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = RMT_LED_STRIP_GPIO_NUM,
        .mem_block_symbols = 64,
        .resolution_hz = RMT_LED_STRIP_RESOLUTION_HZ,
        .trans_queue_depth = 4,
        .flags.with_dma = 1,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&tx_chan_config, &led_chan));

    ESP_LOGI(LED, "Install LED strip encoder");
    rmt_encoder_handle_t led_encoder = NULL;
    led_strip_encoder_config_t encoder_config = {
        .resolution = RMT_LED_STRIP_RESOLUTION_HZ,
    };
    ESP_ERROR_CHECK(rmt_new_led_strip_encoder(&encoder_config, &led_encoder));

    ESP_LOGI(LED, "Enable RMT TX channel");
    ESP_ERROR_CHECK(rmt_enable(led_chan));

    rmt_transmit_config_t tx_config = {.loop_count = 0};

    while (1)
    {
        bool newLedState;
        if (xQueueReceive(ledControlQueue, &newLedState, portMAX_DELAY) == pdTRUE)
        {
            for (int i = 0; i < EXAMPLE_LED_NUMBERS; i++)
            {
                if (newLedState)
                {
                    /* 交替 R/G/B，但峰值限制在 LED_MAX_LEVEL，减少电流波动 */
                    if (i % 3 == 0)
                    {
                        led_strip_pixels[i * 3 + 0] = LED_MAX_LEVEL; // R
                        led_strip_pixels[i * 3 + 1] = LED_MAX_LEVEL;
                        led_strip_pixels[i * 3 + 2] = LED_MAX_LEVEL;
                    }
                    else if (i % 3 == 1)
                    {
                        led_strip_pixels[i * 3 + 0] = LED_MAX_LEVEL;
                        led_strip_pixels[i * 3 + 1] = LED_MAX_LEVEL; // G
                        led_strip_pixels[i * 3 + 2] = LED_MAX_LEVEL;
                    }
                    else
                    {
                        led_strip_pixels[i * 3 + 0] = LED_MAX_LEVEL;
                        led_strip_pixels[i * 3 + 1] = LED_MAX_LEVEL;
                        led_strip_pixels[i * 3 + 2] = LED_MAX_LEVEL; // B
                    }
                }
                else
                {
                    led_strip_pixels[i * 3 + 0] = 0;
                    led_strip_pixels[i * 3 + 1] = 0;
                    led_strip_pixels[i * 3 + 2] = 0;
                }
            }
            ESP_ERROR_CHECK(rmt_transmit(led_chan, led_encoder, led_strip_pixels, sizeof(led_strip_pixels), &tx_config));
            ESP_LOGI(LED, "LED state: %s (R/G/B alternate with capped level)", newLedState ? "ON" : "OFF");
        }
    }
}

/* ---------------------- appInit（关键改动：创建互斥；可选任务绑核） ---------------------- */
void appInit(void)
{
    netOnlineFlag = 1;
    workFlag = 0;

    char ip_str[16];
    snprintf(ip_str, sizeof(ip_str), "192.168.%d.53", ip_third_octet);
    strcpy(deviceAttributeInfo.UDP_serverIP, ip_str);

    dest_addr.sin_addr.s_addr = inet_addr(deviceAttributeInfo.UDP_serverIP);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(deviceAttributeInfo.UDP_serverPort);
    addr_family = AF_INET;
    ip_protocol = IPPROTO_IP;

    udpSock = socket(addr_family, SOCK_DGRAM, ip_protocol);
    if (udpSock < 0)
    {
        ESP_LOGE(UDP, "Unable to create socket: errno %d", errno);
    }

    int send_buffer_size = 64 * 1024;
    int recv_buffer_size = 32 * 1024;
    setsockopt(udpSock, SOL_SOCKET, SO_SNDBUF, &send_buffer_size, sizeof(send_buffer_size));
    setsockopt(udpSock, SOL_SOCKET, SO_RCVBUF, &recv_buffer_size, sizeof(recv_buffer_size));

    /* 创建互斥锁（保护 sensor 操作） */
    sensorMutex = xSemaphoreCreateMutex();
    /* 创建 LED 控制队列 */
    ledControlQueue = xQueueCreate(10, sizeof(bool));

    struct timeval timeout;
    timeout.tv_sec = 5;
    timeout.tv_usec = 0;
    setsockopt(udpSock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    ESP_LOGI(UDP, "Socket created, sending to %s:%d", deviceAttributeInfo.UDP_serverIP, deviceAttributeInfo.UDP_serverPort);

    /* 你工程原来用 xTaskCreate；可保持原样。
       若你们希望更稳，可考虑将 camera_task 固定在 APP CPU，UDP/LED 在另一核：
       xTaskCreatePinnedToCore(camera_task, "camera_task", 1024*50, NULL, 3, &cameraTaskHandle, 1);
       xTaskCreatePinnedToCore(led_task, "led_task", 1024*4, NULL, 2, &ledTaskHandle, 0);
       xTaskCreatePinnedToCore(udpReceive_task, "udpReceive_task", 1024*50, NULL, 4, NULL, 0);
       ★ 请同学根据你们的 FreeRTOS/ESP-IDF 配置核对是否可用 pinned API。
    */
    xTaskCreatePinnedToCore(camera_task, "camera_task", 1024 * 50, NULL, 3, &cameraTaskHandle, 1);
    xTaskCreatePinnedToCore(led_task, "led_task", 1024 * 4, NULL, 2, &ledTaskHandle, 0);
    xTaskCreatePinnedToCore(udpReceive_task, "udpReceive_task", 1024 * 50, NULL, 4, NULL, 0);
    // xTaskCreate(led_task, "led_task", 1024 * 4, NULL, 2, &ledTaskHandle);
    // xTaskCreate(camera_task, "camera_task", 1024 * 50, NULL, 3, &cameraTaskHandle);
    // xTaskCreate(udpReceive_task, "udpReceive_task", 1024 * 50, NULL, 4, NULL);
}