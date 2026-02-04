#include "wifiConnect.h"
#include "httpServer.h"
#include "camera.h"

#define CAMERA_MODEL_AI_THINKER // Has PSRAM

void app_main(void)
{
    char isConnectedFlag = 0;

    ESP_LOGI("main","start wifi sta");
    wifi_init_sta((char *)wifiName,(char *)wifiPassword,&isConnectedFlag);  /* 连接指定的wifi */
    ESP_LOGI("wifiConnect","state = %d",isConnectedFlag);                   /* 判断连接是否成功 */
    if(isConnectedFlag == 0)                                                
    {
        writeWifiInfo((unsigned char *)"111",(unsigned char *)"111",(unsigned char *)"111",1111,(unsigned char *)"fail");   /* 连接失败处理 */
        esp_restart();/* 重启设备 */
    }
    else if(isConnectedFlag == 1)/* 连接成功处理 */
    {
        appInit();
    }   


}
