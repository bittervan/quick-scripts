#!/bin/bash

# 获取所有窗口的信息，包括窗口ID和窗口类
window_list=$(wmctrl -lx)

# 遍历每个窗口，查找窗口类为 "tabby.tabby" 的窗口
echo "$window_list" | while read -r line; do
    # 获取窗口类名
    window_class=$(echo "$line" | awk '{print $3}')
    
    # 如果窗口类名是 "tabby.tabby"，则隐藏该窗口
    if [ "$window_class" == "tabby.tabby" ]; then
        # 提取窗口ID并隐藏窗口
        window_id=$(echo "$line" | awk '{print $1}')
        wmctrl -i -r "$window_id" -b add,minimized
        echo "隐藏窗口：$window_id ($window_class)"
    fi
done
