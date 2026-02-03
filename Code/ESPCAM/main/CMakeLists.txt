idf_component_register( SRCS "led_encoder.c" "main.c" "./src/wifiConnect.c" "./src/httpServer.c" "./src/camera.c"
                        INCLUDE_DIRS "." "./inc"
                        EMBED_FILES "./html/index.html"
                    )
