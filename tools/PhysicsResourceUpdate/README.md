# PhysicsResourceUpdate

仅在明确授权下，为两个不同安装保留原方法/元数据/MVID/引用/常量/其它资源，仅替换指定两物理嵌入资源。拒绝签名PE、链接路径、越界输出和覆盖已有stage；只写全新stage。必须配合ManagedPackageAudit及Sync-AcceptedPhysicsCore的完整IL/资源认证后才应用，并更新来源元数据及正式导出门禁。此工具不改原安装，不复制其它后端，不启动GUI/游戏。

资源新块追加到末段只读区域，原IL/metadata地址不变；ManifestResource偏移与CLI目录/PE大小随之准确更新。旧PDB身份保留，因为MVID与全部方法原样。源码Core正常构建也已通过；安装定向资源更新不代表授权全替换DLL栈或改用户库/模型配置。
