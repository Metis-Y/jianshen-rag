"""数据访问层：各路由与服务通过本包访问数据库，不再就地写 SQL。
分层：routers（校验+包络）→ services（业务编排）→ repositories（SQL 查询）。
"""